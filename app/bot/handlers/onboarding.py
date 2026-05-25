from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.states import BotStates, UserState
from app.db.session import session_factory
from app.services.project_service import (
    create_project_from_source,
    is_link_only,
    set_user_state,
    set_user_type,
)
from app.workers.queue import enqueue_analyze_project

router = Router()

USER_TYPE_LABELS = {
    "channel": "У меня есть канал",
    "client": "Пишу для клиента",
    "niche": "Хочу протестировать на нише",
}


@router.callback_query(F.data.startswith("user_type:"))
async def handle_user_type(callback: CallbackQuery, state: FSMContext) -> None:
    user_type = callback.data.split(":", 1)[1]
    if user_type not in USER_TYPE_LABELS:
        await callback.answer("Неизвестный сценарий")
        return

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
        "— канал конкурента."
    )
    await callback.answer()


@router.message(BotStates.wait_source, F.text)
async def handle_source(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if is_link_only(text):
        await state.update_data(source_link=text)
        async with session_factory()() as session:
            await set_user_state(session, message.from_user, UserState.WAIT_EXAMPLES)
            await session.commit()

        await state.set_state(BotStates.wait_examples)
        await message.answer(
            "Ссылку принял.\n\n"
            "Для MVP пришли 3–5 постов из этого канала одним сообщением. "
            "Так я смогу понять стиль, боли аудитории и сделать первый пост."
        )
        return

    await _save_project_and_ack(message, state, raw_input=text, source_type="text", source_value=None)


@router.message(BotStates.wait_examples, F.text)
async def handle_examples(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    source_link = data.get("source_link")
    await _save_project_and_ack(
        message,
        state,
        raw_input=message.text.strip(),
        source_type="telegram_link_examples",
        source_value=source_link,
    )


async def _save_project_and_ack(
    message: Message,
    state: FSMContext,
    raw_input: str,
    source_type: str,
    source_value: str | None,
) -> None:
    async with session_factory()() as session:
        project = await create_project_from_source(
            session,
            message.from_user,
            source_type=source_type,
            raw_input=raw_input,
            source_value=source_value,
        )
        await session.commit()

    progress = await message.answer("Изучаю материал...")
    await state.update_data(project_id=project.id)
    await state.set_state(BotStates.analyzing)
    enqueue_analyze_project(project.id, message.chat.id, progress.message_id)
