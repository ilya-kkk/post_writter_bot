import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as TelegramUser

from app.bot.keyboards import manual_examples_start_keyboard, manual_examples_submit_keyboard
from app.bot.states import BotStates, UserState
from app.bot.utils.callbacks import mark_callback_chosen
from app.db.session import session_factory
from app.services.project_service import (
    create_project_from_source,
    is_link_only,
    set_user_state,
    set_user_type,
)
from app.services.telegram_client import (
    TelegramClientConfigError,
    TelegramClientOperationError,
    fetch_private_invite_channel_posts,
    format_client_channel_snapshot_for_analysis,
)
from app.services.telegram_public_channel import (
    PublicTelegramChannelError,
    fetch_public_channel_posts,
    format_channel_snapshot_for_analysis,
    is_private_telegram_link,
)
from app.workers.queue import enqueue_analyze_project

router = Router()
logger = logging.getLogger(__name__)
MAX_MANUAL_EXAMPLES = 12
MAX_MANUAL_EXAMPLES_CHARS = 12000

USER_TYPE_LABELS = {
    "channel": "У меня есть канал",
    "client": "Пишу для клиента",
    "niche": "Хочу протестировать на нише",
}


@router.callback_query(F.data.startswith("user_type:"))
async def handle_user_type(callback: CallbackQuery, state: FSMContext) -> None:
    user_type = callback.data.split(":", 1)[1]
    if user_type not in USER_TYPE_LABELS:
        logger.info(
            "onboarding.user_type.unknown user=%s callback=%s",
            _user_for_log(callback.from_user),
            callback.data,
        )
        await callback.answer("Неизвестный сценарий")
        return

    logger.info(
        "onboarding.user_type.selected user=%s user_type=%s",
        _user_for_log(callback.from_user),
        user_type,
    )
    await mark_callback_chosen(callback, USER_TYPE_LABELS[user_type])
    async with session_factory()() as session:
        await set_user_type(session, callback.from_user, user_type)
        await session.commit()

    await state.set_state(BotStates.wait_source)
    await callback.message.answer(
        "Пришли источник, по которому мне понять аудиторию.\n\n"
        "Можно отправить:\n"
        "— ссылку на Telegram-канал;\n"
        "— описание ниши;\n"
        "— несколько примеров постов;\n"
        "— канал конкурента.",
        reply_markup=manual_examples_start_keyboard(),
    )
    await callback.answer()


@router.message(BotStates.wait_source, F.text)
async def handle_source(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    logger.info(
        "onboarding.source.received user=%s chat_id=%s text_len=%s link_only=%s",
        _user_for_log(message.from_user),
        message.chat.id,
        len(text),
        is_link_only(text),
    )
    if is_link_only(text):
        if is_private_telegram_link(text):
            logger.info(
                "onboarding.source.private_link.start user=%s link=%s",
                _user_for_log(message.from_user),
                _link_for_log(text),
            )
            progress = await message.answer(
                "Пробую открыть приватный канал..."
            )
            try:
                snapshot = await fetch_private_invite_channel_posts(text)
            except (TelegramClientConfigError, TelegramClientOperationError) as exc:
                logger.info(
                    "onboarding.source.private_link.failed user=%s link=%s error_type=%s error=%s",
                    _user_for_log(message.from_user),
                    _link_for_log(text),
                    type(exc).__name__,
                    _operation_error_for_log(exc),
                )
                await _switch_to_examples(
                    message,
                    state,
                    text,
                    await _private_channel_fallback_text(exc),
                    progress_message=progress,
                )
                return

            logger.info(
                "onboarding.source.private_link.success user=%s link=%s title=%s entity_id=%s posts=%s",
                _user_for_log(message.from_user),
                _link_for_log(text),
                snapshot.title,
                snapshot.entity_id,
                len(snapshot.posts),
            )
            raw_input = format_client_channel_snapshot_for_analysis(snapshot)
            await _save_project_and_ack(
                message,
                state,
                raw_input=raw_input,
                source_type="telegram_private_invite",
                source_value=text,
                progress_message=progress,
            )
            return

        logger.info(
            "onboarding.source.public_link.start user=%s link=%s",
            _user_for_log(message.from_user),
            _link_for_log(text),
        )
        progress = await message.answer("Пробую прочитать публичный канал...")
        try:
            snapshot = await fetch_public_channel_posts(text)
        except PublicTelegramChannelError as exc:
            logger.info(
                "onboarding.source.public_link.failed user=%s link=%s error=%s",
                _user_for_log(message.from_user),
                _link_for_log(text),
                exc,
            )
            await _switch_to_examples(
                message,
                state,
                text,
                "Ссылку принял, но автоматически прочитать посты не получилось.\n\n"
                "Автопарсинг работает только для открытых публичных каналов "
                "с адресом вида @channel или https://t.me/channel.\n\n"
                "Можешь переслать сюда несколько постов из канала. "
                "Я соберу их и запущу анализ, когда нажмёшь «Готово, отправить».",
                progress_message=progress,
            )
            return

        logger.info(
            "onboarding.source.public_link.success user=%s username=%s source_url=%s posts=%s",
            _user_for_log(message.from_user),
            snapshot.username,
            snapshot.source_url,
            len(snapshot.posts),
        )
        raw_input = format_channel_snapshot_for_analysis(snapshot)
        await _save_project_and_ack(
            message,
            state,
            raw_input=raw_input,
            source_type="telegram_public_link",
            source_value=snapshot.source_url,
            progress_message=progress,
        )
        return

    logger.info(
        "onboarding.source.text.start user=%s chars=%s",
        _user_for_log(message.from_user),
        len(text),
    )
    await _save_project_and_ack(message, state, raw_input=text, source_type="text", source_value=None)


@router.message(BotStates.wait_examples)
async def handle_examples(message: Message, state: FSMContext) -> None:
    text = _extract_example_text(message)
    if not text:
        data = await state.get_data()
        count = len(_manual_examples_from_state(data))
        logger.info(
            "onboarding.examples.empty_message user=%s chat_id=%s existing_count=%s has_forward_origin=%s",
            _user_for_log(message.from_user),
            message.chat.id,
            count,
            _has_forward_origin(message),
        )
        status_text = (
            "В этом сообщении не вижу текста. Перешли пост с текстом или подписью."
            if count == 0
            else f"В этом сообщении не вижу текста.\n\nУже принято: {count}."
        )
        await _replace_examples_status(message, state, status_text, show_submit=count > 0)
        return

    data = await state.get_data()
    examples = _manual_examples_from_state(data)
    if not examples and is_link_only(text):
        logger.info(
            "onboarding.examples.link_received_before_examples user=%s link=%s action=reprocess_as_source",
            _user_for_log(message.from_user),
            _link_for_log(text),
        )
        await handle_source(message, state)
        return

    if len(examples) >= MAX_MANUAL_EXAMPLES:
        logger.info(
            "onboarding.examples.limit_reached user=%s count=%s",
            _user_for_log(message.from_user),
            len(examples),
        )
        await _replace_examples_status(
            message,
            state,
            f"Уже принято {len(examples)} постов. Этого достаточно для анализа.",
            show_submit=True,
        )
        return

    examples.append(text)
    await state.update_data(manual_examples=examples)
    logger.info(
        "onboarding.examples.accepted user=%s chat_id=%s count=%s chars=%s forwarded=%s",
        _user_for_log(message.from_user),
        message.chat.id,
        len(examples),
        len(text),
        _has_forward_origin(message),
    )
    await _replace_examples_status(
        message,
        state,
        _manual_examples_status_text(len(examples)),
        show_submit=True,
    )


@router.callback_query(F.data == "examples:manual")
async def handle_manual_examples_start(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state not in {BotStates.wait_source.state, BotStates.wait_examples.state}:
        logger.info(
            "onboarding.examples.manual_start.ignored user=%s state=%s",
            _user_for_log(callback.from_user),
            current_state,
        )
        await callback.answer()
        return

    logger.info(
        "onboarding.examples.manual_start user=%s state=%s message_id=%s",
        _user_for_log(callback.from_user),
        current_state,
        callback.message.message_id if callback.message else None,
    )
    if callback.message is not None:
        await mark_callback_chosen(callback, "Перешлю посты")
        if current_state == BotStates.wait_source.state:
            async with session_factory()() as session:
                await set_user_state(session, callback.from_user, UserState.WAIT_EXAMPLES)
                await session.commit()
            await state.set_state(BotStates.wait_examples)

        status_message = await callback.message.answer(
            "Ок, пересылай посты из канала сюда. Я буду собирать текст.\n\n"
            "Когда хватит, нажмёшь «Готово, отправить».",
        )
        await state.update_data(manual_examples_status_message_id=status_message.message_id)
        if current_state == BotStates.wait_source.state:
            await state.update_data(source_link=None, manual_examples=[])
    await callback.answer()


@router.callback_query(F.data == "examples:submit")
async def handle_manual_examples_submit(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != BotStates.wait_examples.state:
        logger.info(
            "onboarding.examples.submit.ignored user=%s state=%s",
            _user_for_log(callback.from_user),
            current_state,
        )
        await callback.answer()
        return

    data = await state.get_data()
    examples = _manual_examples_from_state(data)
    if not examples:
        logger.info("onboarding.examples.submit.empty user=%s", _user_for_log(callback.from_user))
        await callback.answer("Сначала перешли хотя бы один пост.", show_alert=True)
        return

    if callback.message is None:
        logger.info("onboarding.examples.submit.no_message user=%s", _user_for_log(callback.from_user))
        await callback.answer("Не получилось отправить материалы. Попробуй ещё раз.", show_alert=True)
        return

    source_link = data.get("source_link")
    raw_input = _format_manual_examples_for_analysis(examples, source_link=source_link)
    logger.info(
        "onboarding.examples.submit user=%s count=%s chars=%s source=%s",
        _user_for_log(callback.from_user),
        len(examples),
        sum(len(example) for example in examples),
        _link_for_log(source_link),
    )
    await mark_callback_chosen(callback, "Готово, отправить")
    await callback.answer()
    await _save_project_and_ack_for_user(
        callback.message,
        state,
        callback.from_user,
        raw_input=raw_input,
        source_type="telegram_link_examples",
        source_value=source_link,
    )


@router.message(BotStates.analyzing, F.text)
async def handle_message_during_analysis(message: Message) -> None:
    logger.info(
        "onboarding.analyzing.message_ignored user=%s chat_id=%s",
        _user_for_log(message.from_user),
        message.chat.id,
    )
    await message.answer("Уже анализирую предыдущий материал. Дождись результата или нажми /new для нового проекта.")


async def _save_project_and_ack(
    message: Message,
    state: FSMContext,
    raw_input: str,
    source_type: str,
    source_value: str | None,
    progress_message: Message | None = None,
) -> None:
    await _save_project_and_ack_for_user(
        message,
        state,
        message.from_user,
        raw_input=raw_input,
        source_type=source_type,
        source_value=source_value,
        progress_message=progress_message,
    )


async def _save_project_and_ack_for_user(
    message: Message,
    state: FSMContext,
    tg_user: TelegramUser,
    raw_input: str,
    source_type: str,
    source_value: str | None,
    progress_message: Message | None = None,
) -> None:
    logger.info(
        "onboarding.project.create.start user=%s source_type=%s source=%s raw_chars=%s progress_message=%s",
        _user_for_log(tg_user),
        source_type,
        _link_for_log(source_value),
        len(raw_input),
        progress_message.message_id if progress_message else None,
    )
    async with session_factory()() as session:
        project = await create_project_from_source(
            session,
            tg_user,
            source_type=source_type,
            raw_input=raw_input,
            source_value=source_value,
        )
        await session.commit()

    logger.info(
        "onboarding.project.create.done user=%s project_id=%s source_type=%s",
        _user_for_log(tg_user),
        project.id,
        source_type,
    )
    if progress_message is None:
        progress = await message.answer("Изучаю материал...")
    else:
        progress = progress_message
        progress = await _safe_edit_or_answer(progress, message, "Изучаю материал...")

    await state.update_data(project_id=project.id)
    await state.set_state(BotStates.analyzing)
    enqueue_analyze_project(project.id, message.chat.id, progress.message_id)
    logger.info(
        "onboarding.analysis.enqueued user=%s project_id=%s chat_id=%s progress_message_id=%s",
        _user_for_log(tg_user),
        project.id,
        message.chat.id,
        progress.message_id,
    )


async def _switch_to_examples(
    message: Message,
    state: FSMContext,
    source_link: str,
    text: str,
    *,
    progress_message: Message | None = None,
) -> None:
    logger.info(
        "onboarding.examples.mode.enter user=%s source=%s progress_message=%s",
        _user_for_log(message.from_user),
        _link_for_log(source_link),
        progress_message.message_id if progress_message else None,
    )
    async with session_factory()() as session:
        await set_user_state(session, message.from_user, UserState.WAIT_EXAMPLES)
        await session.commit()

    await state.set_state(BotStates.wait_examples)
    if progress_message is None:
        status_message = await message.answer(text, reply_markup=manual_examples_start_keyboard())
    else:
        status_message = await _safe_edit_or_answer(
            progress_message,
            message,
            text,
            reply_markup=manual_examples_start_keyboard(),
        )

    await state.update_data(
        source_link=source_link,
        manual_examples=[],
        manual_examples_status_message_id=status_message.message_id,
    )
    logger.info(
        "onboarding.examples.mode.ready user=%s status_message_id=%s",
        _user_for_log(message.from_user),
        status_message.message_id,
    )


async def _replace_examples_status(
    message: Message,
    state: FSMContext,
    text: str,
    *,
    show_submit: bool,
) -> None:
    data = await state.get_data()
    previous_message_id = data.get("manual_examples_status_message_id")
    if previous_message_id:
        await _safe_delete_message(message, previous_message_id)

    status_message = await message.answer(
        text,
        reply_markup=manual_examples_submit_keyboard() if show_submit else None,
    )
    await state.update_data(manual_examples_status_message_id=status_message.message_id)
    logger.info(
        "onboarding.examples.status.replaced user=%s previous_message_id=%s new_message_id=%s show_submit=%s",
        _user_for_log(message.from_user),
        previous_message_id,
        status_message.message_id,
        show_submit,
    )


async def _safe_delete_message(message: Message, message_id: int) -> None:
    try:
        await message.bot.delete_message(message.chat.id, message_id)
    except TelegramBadRequest:
        logger.info(
            "onboarding.message.delete.failed chat_id=%s message_id=%s",
            message.chat.id,
            message_id,
        )
        return
    logger.info(
        "onboarding.message.delete.done chat_id=%s message_id=%s",
        message.chat.id,
        message_id,
    )


async def _private_channel_fallback_text(exc: Exception) -> str:
    base = (
        "Не получилось автоматически прочитать приватный канал.\n\n"
        "Можешь переслать сюда несколько постов из канала. "
        "Я соберу их и запущу анализ, когда нажмёшь «Готово, отправить»."
    )
    if isinstance(exc, TelegramClientOperationError):
        if exc.code == "join_request_pending":
            return (
                "Отправил заявку на вступление, но доступ к каналу пока не появился.\n\n"
                "Если заявка подтвердится автоматически, отправь ссылку ещё раз. "
                "Либо перешли сюда несколько постов вручную."
            )
        if exc.code == "telegram_client_not_authorized":
            return (
                "Не получилось автоматически открыть приватный канал.\n\n"
                "Можешь переслать сюда несколько постов вручную."
            )
        if exc.code == "unsupported_private_link":
            return (
                "Это приватная ссылка Telegram, но в ней нет invite-кода для вступления.\n\n"
                "Пришли invite-ссылку вида https://t.me/+... или перешли несколько постов вручную."
            )
        if exc.code == "invalid_invite_link":
            return (
                "Telegram не принял invite-ссылку: она может быть устаревшей или отозванной.\n\n"
                "Пришли новую invite-ссылку или перешли несколько постов вручную."
            )
    return base


async def _safe_edit_or_answer(
    progress: Message,
    source_message: Message,
    text: str,
    reply_markup=None,
) -> Message:
    try:
        await progress.edit_text(text, reply_markup=reply_markup)
        return progress
    except TelegramBadRequest:
        return await source_message.answer(text, reply_markup=reply_markup)


def _extract_example_text(message: Message) -> str | None:
    text = message.text or message.caption
    if text is None:
        return None

    normalized = text.replace("\xa0", " ").strip()
    return normalized or None


def _manual_examples_from_state(data: dict) -> list[str]:
    examples = data.get("manual_examples")
    if not isinstance(examples, list):
        return []

    return [example for example in examples if isinstance(example, str) and example.strip()]


def _manual_examples_status_text(count: int) -> str:
    plural = _post_plural(count)
    return (
        f"Принял {count} {plural}.\n\n"
        "Можешь переслать ещё или нажать «Готово, отправить»."
    )


def _format_manual_examples_for_analysis(examples: list[str], *, source_link: str | None) -> str:
    parts = ["Источник: примеры постов из Telegram-канала"]
    if source_link:
        parts.append(f"Ссылка: {source_link}")
    parts.extend(["", "Примеры постов:"])

    for index, example in enumerate(examples, start=1):
        parts.append(f"\nПост {index}:\n{example.strip()}")

    material = "\n".join(parts).strip()
    if len(material) <= MAX_MANUAL_EXAMPLES_CHARS:
        return material

    return material[: MAX_MANUAL_EXAMPLES_CHARS - 15].rstrip() + "\n\n[обрезано]"


def _post_plural(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "пост"
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return "поста"
    return "постов"


def _user_for_log(user: TelegramUser | None) -> str:
    if user is None:
        return "unknown"
    return f"id={user.id} username={user.username or '-'}"


def _link_for_log(value: str | None) -> str:
    if not value:
        return "-"
    if is_private_telegram_link(value):
        marker = value.rsplit("/", 1)[-1]
        if marker.startswith("+"):
            marker = marker[1:]
        return f"private:{_mask_token(marker)}"
    if len(value) > 96:
        return value[:93] + "..."
    return value


def _mask_token(value: str) -> str:
    if len(value) <= 8:
        return f"{value[:2]}***{value[-2:]}(len={len(value)})"
    return f"{value[:4]}***{value[-4:]}(len={len(value)})"


def _operation_error_for_log(exc: Exception) -> str:
    if isinstance(exc, TelegramClientOperationError):
        return f"code={exc.code} retry_after={exc.retry_after_seconds} message={exc.message}"
    return str(exc)


def _has_forward_origin(message: Message) -> bool:
    return bool(getattr(message, "forward_origin", None))
