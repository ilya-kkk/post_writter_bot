import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from sqlalchemy import select

from app.bot.keyboards import (
    analysis_confirmation_keyboard,
    ideas_keyboard,
    main_menu_reply_keyboard,
    project_actions_keyboard,
    tariff_keyboard,
)
from app.bot.messages import (
    format_audience_profile,
    format_ideas,
    free_post_explanation,
    idea_to_dict,
    paywall_text,
    profile_to_dict,
)
from app.bot.states import UserState
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models import AudienceProfile, Idea, Post, Project, User
from app.db.session import session_factory
from app.services.audience_analysis import analyze_audience
from app.services.followup_service import create_followup_events
from app.services.idea_generation import generate_ideas
from app.services.payment_service import get_active_subscription_for_user_id
from app.services.post_generation import generate_post
from app.services.project_service import get_current_ideas

logger = logging.getLogger(__name__)


def analyze_project_job(project_id: int, chat_id: int, progress_message_id: int) -> None:
    configure_logging()
    asyncio.run(_analyze_project(project_id, chat_id, progress_message_id))


def generate_ideas_job(project_id: int, chat_id: int, progress_message_id: int) -> None:
    configure_logging()
    asyncio.run(_generate_ideas(project_id, chat_id, progress_message_id))


def generate_post_job(project_id: int, idea_id: int, chat_id: int, progress_message_id: int) -> None:
    configure_logging()
    asyncio.run(_generate_post(project_id, idea_id, chat_id, progress_message_id))


def _make_bot() -> Bot:
    return Bot(settings.bot_token, session=AiohttpSession(timeout=settings.telegram_timeout_seconds))


async def _analyze_project(project_id: int, chat_id: int, progress_message_id: int) -> None:
    bot = _make_bot()
    try:
        await _show_analysis_progress(bot, chat_id, progress_message_id)
        async with session_factory()() as session:
            project = await session.get(Project, project_id)
            if project is None:
                logger.warning("Project %s not found", project_id)
                return
            raw_input = project.raw_input

        try:
            analysis = await analyze_audience(raw_input)
        except Exception:
            logger.exception("Audience analysis failed for project %s", project_id)
            await _mark_project_failed(project_id)
            await _safe_edit_or_send(
                bot,
                chat_id,
                progress_message_id,
                "Не смог завершить анализ. Пришли материал ещё раз или попробуй позже.",
            )
            return

        async with session_factory()() as session:
            project = await session.get(Project, project_id)
            if project is None:
                logger.warning("Project %s disappeared before analysis save", project_id)
                return
            profile = await session.scalar(select(AudienceProfile).where(AudienceProfile.project_id == project_id))
            if profile is None:
                profile = AudienceProfile(project_id=project_id)
                session.add(profile)

            profile.niche = analysis["niche"]
            profile.audience_summary = analysis["audience_summary"]
            profile.pains_json = analysis["pains"]
            profile.desires_json = analysis["desires"]
            profile.beliefs_json = analysis["beliefs"]
            profile.tone_json = analysis["tone_of_voice"]
            profile.raw_analysis_json = analysis
            project.status = "analysis_ready"

            user = await session.get(User, project.user_id)
            if user:
                user.current_state = UserState.SHOW_ANALYSIS

            await session.commit()
            await session.refresh(profile)
            profile_text = format_audience_profile(profile)

        await _safe_edit_or_send(
            bot,
            chat_id,
            progress_message_id,
            profile_text,
            reply_markup=analysis_confirmation_keyboard(project_id),
        )
    finally:
        await bot.session.close()


async def _generate_ideas(project_id: int, chat_id: int, progress_message_id: int) -> None:
    bot = _make_bot()
    try:
        async with session_factory()() as session:
            project = await session.get(Project, project_id)
            profile = await session.scalar(select(AudienceProfile).where(AudienceProfile.project_id == project_id))
            if project is None or profile is None:
                await _safe_edit(bot, chat_id, progress_message_id, "Не нашёл анализ. Пришли материал ещё раз.")
                return
            identity = profile_to_dict(profile)

        await _safe_edit(bot, chat_id, progress_message_id, "Подбираю идеи...\n\n✅ Смотрю боли аудитории")
        ideas_data = await generate_ideas(identity, count=6)
        await _safe_edit(
            bot,
            chat_id,
            progress_message_id,
            "Подбираю идеи...\n\n✅ Смотрю боли аудитории\n✅ Ищу продающие углы\n✅ Собираю список тем",
        )

        async with session_factory()() as session:
            project = await session.get(Project, project_id)
            if project is None:
                logger.warning("Project %s disappeared before ideas save", project_id)
                return
            profile = await session.scalar(select(AudienceProfile).where(AudienceProfile.project_id == project_id))
            if profile is None:
                await _safe_edit_or_send(bot, chat_id, progress_message_id, "Не нашёл анализ. Пришли материал ещё раз.")
                return
            for item in ideas_data:
                session.add(
                    Idea(
                        project_id=project_id,
                        title=item["title"],
                        description=item["description"],
                        angle=item["angle"],
                    )
                )

            project.status = "ideas_ready"
            user = await session.get(User, project.user_id)
            if user:
                user.current_state = UserState.WAIT_IDEA_SELECTION

            await session.commit()
            ideas = await get_current_ideas(session, project_id)

        await _safe_edit_or_send(
            bot,
            chat_id,
            progress_message_id,
            format_ideas(ideas),
            reply_markup=ideas_keyboard(len(ideas), project_id),
        )
    finally:
        await bot.session.close()


async def _generate_post(project_id: int, idea_id: int, chat_id: int, progress_message_id: int) -> None:
    bot = _make_bot()
    try:
        async with session_factory()() as session:
            project = await session.get(Project, project_id)
            profile = await session.scalar(select(AudienceProfile).where(AudienceProfile.project_id == project_id))
            idea = await session.get(Idea, idea_id)
            if project is None or profile is None or idea is None:
                await _safe_edit(bot, chat_id, progress_message_id, "Не нашёл идею. Выбери тему ещё раз.")
                return
            user = await session.get(User, project.user_id)
            subscription = await get_active_subscription_for_user_id(session, project.user_id)

            if subscription and subscription.posts_used >= subscription.posts_limit:
                if user:
                    user.current_state = UserState.WAIT_TARIFF_SELECTION
                await session.commit()
                await _safe_edit(bot, chat_id, progress_message_id, "Лимит постов по подписке закончился.")
                await bot.send_message(chat_id, paywall_text(), reply_markup=tariff_keyboard())
                return

            identity = profile_to_dict(profile)
            idea_data = idea_to_dict(idea)
            generation_type = "paid" if subscription else "free"
            cta = (
                "мягко предложи читателю написать автору или сделать следующий шаг по теме; "
                "не упоминай тарифы, подписку и этого бота"
                if subscription
                else "Выбери тариф и получай такие посты регулярно."
            )

        await _safe_edit(
            bot,
            chat_id,
            progress_message_id,
            "Генерирую пост по выбранной идее...\n\n✅ Собираю структуру\n✅ Подстраиваю стиль",
        )
        text = await generate_post(identity, idea_data, cta=cta)

        async with session_factory()() as session:
            project = await session.get(Project, project_id)
            idea = await session.get(Idea, idea_id)
            if project is None or idea is None:
                logger.warning("Project %s or idea %s disappeared before post save", project_id, idea_id)
                return
            user = await session.get(User, project.user_id)
            subscription = await get_active_subscription_for_user_id(session, project.user_id)
            post = Post(
                project_id=project_id,
                idea_id=idea_id,
                text=text,
                generation_type=generation_type,
                identity_json=identity,
            )
            session.add(post)
            project.status = "post_ready" if subscription else "free_post_ready"

            if subscription:
                subscription.posts_used += 1
                if user:
                    user.current_state = UserState.SUBSCRIBED
            elif user:
                user.current_state = UserState.PAYWALL_SHOWN
                await create_followup_events(session, user.id)

            await session.commit()

        await _safe_edit(bot, chat_id, progress_message_id, "Пост готов. Отправляю ниже.")
        await _send_long_message(bot, chat_id, text)
        if subscription:
            await bot.send_message(chat_id, "Готово. Можно продолжить работу с этим проектом.", reply_markup=main_menu_reply_keyboard())
            await bot.send_message(chat_id, "Что дальше?", reply_markup=project_actions_keyboard(project_id))
        else:
            await bot.send_message(chat_id, free_post_explanation())
            await bot.send_message(chat_id, paywall_text(), reply_markup=tariff_keyboard())
    finally:
        await bot.session.close()


async def _show_analysis_progress(bot: Bot, chat_id: int, message_id: int) -> None:
    steps = [
        "Изучаю материал...\n\n✅ Определяю нишу",
        "Изучаю материал...\n\n✅ Определяю нишу\n✅ Выделяю сегменты аудитории",
        "Изучаю материал...\n\n✅ Определяю нишу\n✅ Выделяю сегменты аудитории\n✅ Ищу боли и желания",
        "Изучаю материал...\n\n✅ Определяю нишу\n✅ Выделяю сегменты аудитории\n✅ Ищу боли и желания\n✅ Смотрю стиль текста",
        (
            "Изучаю материал...\n\n"
            "✅ Определяю нишу\n"
            "✅ Выделяю сегменты аудитории\n"
            "✅ Ищу боли и желания\n"
            "✅ Смотрю стиль текста\n"
            "✅ Формирую профиль ЦА"
        ),
    ]
    for step in steps:
        await _safe_edit(bot, chat_id, message_id, step)
        await asyncio.sleep(2)


async def _safe_edit(bot: Bot, chat_id: int, message_id: int, text: str, reply_markup=None) -> bool:
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        return True
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        logger.info("Could not edit message %s: %s", message_id, exc)
        return False


async def _safe_edit_or_send(bot: Bot, chat_id: int, message_id: int, text: str, reply_markup=None) -> None:
    if await _safe_edit(bot, chat_id, message_id, text, reply_markup=reply_markup):
        return

    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramNetworkError as exc:
        logger.info("Could not send fallback message to chat %s: %s", chat_id, exc)


async def _mark_project_failed(project_id: int) -> None:
    async with session_factory()() as session:
        project = await session.get(Project, project_id)
        if project is None:
            return

        project.status = "analysis_failed"
        user = await session.get(User, project.user_id)
        if user and user.current_project_id == project_id:
            user.current_state = UserState.WAIT_SOURCE
        await session.commit()


async def _send_long_message(bot: Bot, chat_id: int, text: str) -> None:
    max_len = 3900
    for start in range(0, len(text), max_len):
        await bot.send_message(chat_id, text[start : start + max_len])
