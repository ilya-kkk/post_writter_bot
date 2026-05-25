from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.states import BotStates, UserState
from app.db.session import session_factory
from app.services.project_service import get_latest_project_for_tg_user, set_user_state
from app.workers.queue import enqueue_generate_ideas

router = Router()


@router.callback_query(F.data == "analysis:confirm")
async def confirm_analysis(callback: CallbackQuery, state: FSMContext) -> None:
    project_id = await _resolve_project_id(callback, state)
    if project_id is None:
        await callback.answer("Не нашёл проект. Пришли описание ещё раз.")
        return

    async with session_factory()() as session:
        await set_user_state(session, callback.from_user, UserState.GENERATING_IDEAS)
        await session.commit()

    await state.update_data(project_id=project_id)
    await state.set_state(BotStates.generating_ideas)
    progress = await callback.message.answer("Подбираю идеи для постов...")
    enqueue_generate_ideas(project_id, callback.message.chat.id, progress.message_id)
    await callback.answer()


@router.callback_query(F.data == "analysis:edit")
async def edit_analysis(callback: CallbackQuery, state: FSMContext) -> None:
    async with session_factory()() as session:
        await set_user_state(session, callback.from_user, UserState.WAIT_SOURCE)
        await session.commit()

    await state.set_state(BotStates.wait_source)
    await callback.message.answer("Ок, пришли новое описание ниши или 3–5 примеров постов одним сообщением.")
    await callback.answer()


async def _resolve_project_id(callback: CallbackQuery, state: FSMContext) -> int | None:
    data = await state.get_data()
    project_id = data.get("project_id")
    if project_id:
        return int(project_id)

    async with session_factory()() as session:
        project = await get_latest_project_for_tg_user(session, callback.from_user.id)
        return project.id if project else None
