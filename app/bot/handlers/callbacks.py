from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.states import BotStates, UserState
from app.bot.utils.callbacks import mark_callback_chosen
from app.db.session import session_factory
from app.services.project_service import (
    get_latest_project_for_tg_user,
    get_projects_for_tg_user,
    get_project_for_tg_user,
    set_current_project_for_tg_user,
    set_user_state,
)
from app.workers.queue import enqueue_generate_ideas

router = Router()


@router.callback_query(F.data.startswith("analysis:confirm"))
async def confirm_analysis(callback: CallbackQuery, state: FSMContext) -> None:
    explicit_project_id = _project_id_from_callback(callback.data)
    project_id = explicit_project_id or await _resolve_project_id(callback, state)
    if project_id is None:
        await callback.answer("Не нашёл проект. Пришли описание ещё раз.")
        return

    async with session_factory()() as session:
        project = await get_project_for_tg_user(session, callback.from_user.id, project_id)
        if explicit_project_id is None and not _project_is_ready(project):
            project = await _latest_ready_project(session, callback.from_user.id)
            if project is not None:
                project_id = project.id

        if project is None:
            await callback.answer("Проект не найден", show_alert=True)
            return
        if not _project_is_ready(project):
            await callback.answer("Анализ ещё не готов. Дождись результата.", show_alert=True)
            return

        await set_current_project_for_tg_user(session, callback.from_user.id, project.id)
        await set_user_state(session, callback.from_user, UserState.GENERATING_IDEAS)
        await session.commit()

    await state.update_data(project_id=project_id)
    await state.set_state(BotStates.generating_ideas)
    await mark_callback_chosen(callback, "Да, всё верно")
    progress = await callback.message.answer("Подбираю идеи для постов...")
    enqueue_generate_ideas(project_id, callback.message.chat.id, progress.message_id)
    await callback.answer()


@router.callback_query(F.data.startswith("analysis:edit"))
async def edit_analysis(callback: CallbackQuery, state: FSMContext) -> None:
    async with session_factory()() as session:
        await set_user_state(session, callback.from_user, UserState.WAIT_SOURCE)
        await session.commit()

    await state.set_state(BotStates.wait_source)
    await mark_callback_chosen(callback, "Изменить описание")
    await callback.message.answer("Ок, пришли новое описание ниши, ссылку или несколько примеров постов.")
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


def _project_is_ready(project) -> bool:
    return project is not None and project.status == "analysis_ready" and project.audience_profile is not None


async def _latest_ready_project(session, telegram_id: int):
    projects = await get_projects_for_tg_user(session, telegram_id)
    for project in projects:
        if _project_is_ready(project):
            return project
    return None
