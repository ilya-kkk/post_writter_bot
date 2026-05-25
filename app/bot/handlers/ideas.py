from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.states import BotStates, UserState
from app.db.session import session_factory
from app.services.project_service import get_current_ideas, get_latest_project_for_tg_user, set_user_state
from app.workers.queue import enqueue_generate_ideas, enqueue_generate_post

router = Router()


@router.callback_query(F.data == "ideas:regenerate")
async def regenerate_ideas(callback: CallbackQuery, state: FSMContext) -> None:
    project_id = await _resolve_project_id(callback, state)
    if project_id is None:
        await callback.answer("Не нашёл проект. Пришли описание ещё раз.")
        return

    async with session_factory()() as session:
        await set_user_state(session, callback.from_user, UserState.GENERATING_IDEAS)
        await session.commit()

    await state.update_data(project_id=project_id)
    await state.set_state(BotStates.generating_ideas)
    progress = await callback.message.answer("Генерирую другие идеи...")
    enqueue_generate_ideas(project_id, callback.message.chat.id, progress.message_id)
    await callback.answer()


@router.callback_query(F.data.startswith("idea:select:"))
async def select_idea(callback: CallbackQuery, state: FSMContext) -> None:
    project_id = await _resolve_project_id(callback, state)
    if project_id is None:
        await callback.answer("Не нашёл проект. Пришли описание ещё раз.")
        return

    index = int(callback.data.rsplit(":", 1)[1]) - 1
    async with session_factory()() as session:
        ideas = await get_current_ideas(session, project_id)
        if index < 0 or index >= len(ideas):
            await callback.answer("Не нашёл эту идею")
            return
        idea = ideas[index]
        await set_user_state(session, callback.from_user, UserState.GENERATING_POST)
        await session.commit()

    await state.update_data(project_id=project_id, idea_id=idea.id)
    await state.set_state(BotStates.generating_post)
    progress = await callback.message.answer(
        "Генерирую пост по выбранной идее...\n"
        "Это может занять до минуты."
    )
    enqueue_generate_post(project_id, idea.id, callback.message.chat.id, progress.message_id)
    await callback.answer()


async def _resolve_project_id(callback: CallbackQuery, state: FSMContext) -> int | None:
    data = await state.get_data()
    project_id = data.get("project_id")
    if project_id:
        return int(project_id)

    async with session_factory()() as session:
        project = await get_latest_project_for_tg_user(session, callback.from_user.id)
        return project.id if project else None
