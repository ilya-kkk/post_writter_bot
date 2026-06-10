from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.states import BotStates, UserState
from app.db.session import session_factory
from app.services.project_service import (
    get_current_ideas,
    get_latest_project_for_tg_user,
    get_projects_for_tg_user,
    get_project_for_tg_user,
    set_current_project_for_tg_user,
    set_user_state,
)
from app.workers.queue import enqueue_generate_ideas, enqueue_generate_post

router = Router()


@router.callback_query(F.data.startswith("ideas:regenerate"))
async def regenerate_ideas(callback: CallbackQuery, state: FSMContext) -> None:
    explicit_project_id = _project_id_from_callback(callback.data)
    project_id = explicit_project_id or await _resolve_project_id(callback, state)
    if project_id is None:
        await callback.answer("Не нашёл проект. Пришли описание ещё раз.")
        return

    async with session_factory()() as session:
        project = await get_project_for_tg_user(session, callback.from_user.id, project_id)
        if explicit_project_id is None and not _project_has_analysis(project):
            project = await _latest_ready_project(session, callback.from_user.id)
            if project is not None:
                project_id = project.id

        if project is None:
            await callback.answer("Проект не найден", show_alert=True)
            return
        if not _project_has_analysis(project):
            await callback.answer("По этому проекту ещё нет анализа.", show_alert=True)
            return

        await set_current_project_for_tg_user(session, callback.from_user.id, project.id)
        await set_user_state(session, callback.from_user, UserState.GENERATING_IDEAS)
        await session.commit()

    await state.update_data(project_id=project_id)
    await state.set_state(BotStates.generating_ideas)
    progress = await callback.message.answer("Генерирую другие идеи...")
    enqueue_generate_ideas(project_id, callback.message.chat.id, progress.message_id)
    await callback.answer()


@router.callback_query(F.data.startswith("idea:select:"))
async def select_idea(callback: CallbackQuery, state: FSMContext) -> None:
    callback_project_id, index = _parse_idea_selection(callback.data)
    project_id = callback_project_id or await _resolve_project_id(callback, state)
    if project_id is None:
        await callback.answer("Не нашёл проект. Пришли описание ещё раз.")
        return

    async with session_factory()() as session:
        ideas = await get_current_ideas(session, project_id)
        if index < 0 or index >= len(ideas):
            await callback.answer("Не нашёл эту идею")
            return
        idea = ideas[index]
        await set_current_project_for_tg_user(session, callback.from_user.id, project_id)
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


def _project_id_from_callback(data: str | None) -> int | None:
    if not data:
        return None
    parts = data.rsplit(":", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


def _parse_idea_selection(data: str | None) -> tuple[int | None, int]:
    if not data:
        return None, -1
    parts = data.split(":")
    if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
        return int(parts[2]), int(parts[3]) - 1
    if len(parts) == 3 and parts[2].isdigit():
        return None, int(parts[2]) - 1
    return None, -1


def _project_has_analysis(project) -> bool:
    return project is not None and project.audience_profile is not None


async def _latest_ready_project(session, telegram_id: int):
    projects = await get_projects_for_tg_user(session, telegram_id)
    for project in projects:
        if _project_has_analysis(project):
            return project
    return None
