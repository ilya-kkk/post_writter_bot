from datetime import UTC

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User as TelegramUser
from sqlalchemy import select

from app.bot.keyboards import (
    main_menu_reply_keyboard,
    project_actions_keyboard,
    subscription_menu_keyboard,
    tariff_keyboard,
)
from app.bot.messages import paywall_text, subscription_menu_text, subscription_status_text
from app.bot.states import BotStates, UserState
from app.bot.utils.callbacks import mark_callback_chosen
from app.db.models import AudienceProfile, Idea, Project
from app.db.session import session_factory
from app.services.payment_service import get_active_subscription_for_tg_user
from app.services.project_service import (
    get_current_project_for_tg_user,
    get_project_for_tg_user,
    get_projects_for_tg_user,
    set_current_project_for_tg_user,
    set_user_state,
)
from app.workers.queue import enqueue_generate_ideas, enqueue_generate_post

router = Router()

SOURCE_REQUEST_TEXT = (
    "Пришли источник, по которому мне понять аудиторию.\n\n"
    "Можно отправить:\n"
    "— ссылку на Telegram-канал;\n"
    "— описание ниши;\n"
    "— несколько примеров постов;\n"
    "— канал конкурента."
)


@router.message(Command("menu"))
async def menu_command(message: Message) -> None:
    await _show_main_menu(message, message.from_user)


@router.message(F.text == "Меню")
async def menu_button(message: Message) -> None:
    await _show_main_menu(message, message.from_user)


@router.message(Command("new"))
async def new_project_command(message: Message, state: FSMContext) -> None:
    await _start_new_project(message, state, message.from_user)


@router.message(Command("ideas"))
async def ideas_command(message: Message, state: FSMContext) -> None:
    await _start_ideas_generation(message, state, message.from_user)


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    await _show_subscription_status(message, message.from_user)


@router.callback_query(F.data == "menu:projects")
async def projects_callback(callback: CallbackQuery) -> None:
    await mark_callback_chosen(callback, "Мои проекты")
    await _show_projects(callback.message, callback.from_user)
    await callback.answer()


@router.callback_query(F.data == "menu:new_project")
async def new_project_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await mark_callback_chosen(callback, "Создать новый проект")
    await _start_new_project(callback.message, state, callback.from_user)
    await callback.answer()


@router.callback_query(F.data == "menu:status")
async def status_callback(callback: CallbackQuery) -> None:
    await mark_callback_chosen(callback, "Статус подписки")
    await _show_subscription_status(callback.message, callback.from_user)
    await callback.answer()


@router.callback_query(F.data == "menu:tariffs")
async def tariffs_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BotStates.wait_tariff_selection)
    await mark_callback_chosen(callback, "Тарифы")
    await callback.message.answer(paywall_text(), reply_markup=tariff_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:back")
async def back_to_menu_callback(callback: CallbackQuery) -> None:
    await mark_callback_chosen(callback, "Назад в меню")
    await _show_main_menu(callback.message, callback.from_user)
    await callback.answer()


@router.callback_query(F.data.startswith("project:select:"))
async def select_project_callback(callback: CallbackQuery, state: FSMContext) -> None:
    project_id = int(callback.data.rsplit(":", 1)[1])
    async with session_factory()() as session:
        project = await set_current_project_for_tg_user(session, callback.from_user.id, project_id)
        if project is None:
            await callback.answer("Проект не найден")
            return
        await set_user_state(session, callback.from_user, UserState.SUBSCRIBED)
        await session.commit()

    await state.update_data(project_id=project.id)
    await state.set_state(BotStates.subscribed)
    await mark_callback_chosen(callback, _project_title(project))
    await callback.message.answer(
        f"Проект выбран: {_project_title(project)}\n\nЧто делаем дальше?",
        reply_markup=project_actions_keyboard(project.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("project:ideas:"))
async def project_ideas_callback(callback: CallbackQuery, state: FSMContext) -> None:
    project_id = int(callback.data.rsplit(":", 1)[1])
    await mark_callback_chosen(callback, "Сгенерировать темы")
    await _start_ideas_generation(callback.message, state, callback.from_user, project_id=project_id)
    await callback.answer()


@router.callback_query(F.data.startswith("project:custom_topic:"))
async def custom_topic_callback(callback: CallbackQuery, state: FSMContext) -> None:
    project_id = int(callback.data.rsplit(":", 1)[1])
    await mark_callback_chosen(callback, "Написать свою тему")
    async with session_factory()() as session:
        subscription = await get_active_subscription_for_tg_user(session, callback.from_user.id)
        project = await set_current_project_for_tg_user(session, callback.from_user.id, project_id)
        if subscription is None:
            await state.set_state(BotStates.wait_tariff_selection)
            await callback.message.answer(paywall_text(), reply_markup=tariff_keyboard())
            await callback.answer()
            return
        if project is None or project.audience_profile is None:
            await callback.message.answer("По этому проекту ещё нет анализа. Создай проект заново или дождись анализа.")
            await callback.answer()
            return
        await set_user_state(session, callback.from_user, UserState.WAIT_CUSTOM_TOPIC)
        await session.commit()

    await state.update_data(project_id=project_id)
    await state.set_state(BotStates.wait_custom_topic)
    await callback.message.answer(
        "Напиши тему поста одним сообщением. Я сохраню её в проекте и напишу пост в его стилистике.",
        reply_markup=main_menu_reply_keyboard(),
    )
    await callback.answer()


@router.message(BotStates.wait_custom_topic, F.text)
async def handle_custom_topic(message: Message, state: FSMContext) -> None:
    topic = message.text.strip()
    if not topic:
        await message.answer("Пришли тему текстом.")
        return

    data = await state.get_data()
    project_id = int(data.get("project_id") or 0)
    async with session_factory()() as session:
        subscription = await get_active_subscription_for_tg_user(session, message.from_user.id)
        project = await get_project_for_tg_user(session, message.from_user.id, project_id)
        profile = None
        if project is not None:
            profile = await session.scalar(select(AudienceProfile).where(AudienceProfile.project_id == project.id))

        if subscription is None:
            await state.set_state(BotStates.wait_tariff_selection)
            await message.answer(paywall_text(), reply_markup=tariff_keyboard())
            return
        if project is None or profile is None:
            await message.answer("Не нашёл выбранный проект. Открой Меню и выбери проект ещё раз.")
            return

        idea = Idea(
            project_id=project.id,
            title=topic[:500],
            description=f"Пост по теме пользователя: {topic}",
            angle="Раскрыть тему в сохранённой стилистике проекта и привести к мягкому следующему шагу.",
        )
        session.add(idea)
        await set_user_state(session, message.from_user, UserState.GENERATING_POST)
        await session.commit()
        await session.refresh(idea)

    await state.update_data(project_id=project_id, idea_id=idea.id)
    await state.set_state(BotStates.generating_post)
    progress = await message.answer(
        "Генерирую пост по твоей теме...\nЭто может занять до минуты.",
        reply_markup=main_menu_reply_keyboard(),
    )
    enqueue_generate_post(project_id, idea.id, message.chat.id, progress.message_id)


async def _show_main_menu(message: Message, tg_user: TelegramUser) -> None:
    async with session_factory()() as session:
        subscription = await get_active_subscription_for_tg_user(session, tg_user.id)

    if subscription is None:
        await message.answer(paywall_text(), reply_markup=tariff_keyboard())
        return

    await message.answer(subscription_menu_text(), reply_markup=subscription_menu_keyboard())


async def _show_projects(message: Message, tg_user: TelegramUser) -> None:
    async with session_factory()() as session:
        subscription = await get_active_subscription_for_tg_user(session, tg_user.id)
        if subscription is None:
            await message.answer(paywall_text(), reply_markup=tariff_keyboard())
            return
        projects = await get_projects_for_tg_user(session, tg_user.id)

    if not projects:
        await message.answer(
            "Проектов пока нет. Создай первый проект, чтобы я запомнил тематику и стиль.",
            reply_markup=subscription_menu_keyboard(),
        )
        return

    await message.answer("Вот твои проекты. Выбери тематику:", reply_markup=_projects_keyboard(projects))


async def _start_new_project(message: Message, state: FSMContext, tg_user: TelegramUser) -> None:
    await state.clear()
    async with session_factory()() as session:
        await set_user_state(session, tg_user, UserState.WAIT_SOURCE)
        await session.commit()

    await state.set_state(BotStates.wait_source)
    await message.answer(SOURCE_REQUEST_TEXT, reply_markup=main_menu_reply_keyboard())


async def _start_ideas_generation(
    message: Message,
    state: FSMContext,
    tg_user: TelegramUser,
    *,
    project_id: int | None = None,
) -> None:
    async with session_factory()() as session:
        subscription = await get_active_subscription_for_tg_user(session, tg_user.id)
        if subscription is None:
            await state.set_state(BotStates.wait_tariff_selection)
            await message.answer(paywall_text(), reply_markup=tariff_keyboard())
            return

        project = (
            await get_project_for_tg_user(session, tg_user.id, project_id)
            if project_id is not None
            else await get_current_project_for_tg_user(session, tg_user.id)
        )
        if project is None:
            await _show_projects(message, tg_user)
            return

        profile = await session.scalar(select(AudienceProfile).where(AudienceProfile.project_id == project.id))
        if profile is None:
            await message.answer("По этому проекту ещё нет анализа. Пришли источник заново или дождись анализа.")
            return

        await set_current_project_for_tg_user(session, tg_user.id, project.id)
        await set_user_state(session, tg_user, UserState.GENERATING_IDEAS)
        await session.commit()

    await state.update_data(project_id=project.id)
    await state.set_state(BotStates.generating_ideas)
    progress = await message.answer("Подбираю темы для выбранного проекта...", reply_markup=main_menu_reply_keyboard())
    enqueue_generate_ideas(project.id, message.chat.id, progress.message_id)


async def _show_subscription_status(message: Message, tg_user: TelegramUser) -> None:
    async with session_factory()() as session:
        subscription = await get_active_subscription_for_tg_user(session, tg_user.id)

    if subscription is None:
        await message.answer(paywall_text(), reply_markup=tariff_keyboard())
        return

    expires_at = subscription.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    expires_text = expires_at.astimezone(UTC).strftime("%d.%m.%Y")
    await message.answer(
        subscription_status_text(
            posts_used=subscription.posts_used,
            posts_limit=subscription.posts_limit,
            projects_limit=subscription.projects_limit,
            expires_at=expires_text,
        ),
        reply_markup=subscription_menu_keyboard(),
    )


def _projects_keyboard(projects: list[Project]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_project_title(project), callback_data=f"project:select:{project.id}")]
        for project in projects
    ]
    rows.append([InlineKeyboardButton(text="Создать новый проект", callback_data="menu:new_project")])
    rows.append([InlineKeyboardButton(text="Назад в меню", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _project_title(project: Project) -> str:
    profile = project.audience_profile
    if profile and profile.niche:
        title = profile.niche
    elif project.source_value:
        title = project.source_value
    else:
        title = f"Проект #{project.id}"

    created_at = project.created_at.strftime("%d.%m") if project.created_at else ""
    prefix = f"{created_at} · " if created_at else ""
    max_len = 52 - len(prefix)
    if len(title) > max_len:
        title = title[: max_len - 1].rstrip() + "…"
    return f"{prefix}{title}"
