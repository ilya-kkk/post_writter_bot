import re

from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.states import UserState
from app.db.models import Idea, Project, User

LINK_RE = re.compile(r"^(https?://)?(t\.me|telegram\.me)/[A-Za-z0-9_+/.-]+/?$")


def is_link_only(text: str) -> bool:
    value = text.strip()
    if "\n" in value or len(value) > 120:
        return False
    return bool(LINK_RE.match(value) or value.startswith("@"))


async def upsert_user(session: AsyncSession, tg_user: TelegramUser, state: str | None = None) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            current_state=state or UserState.START,
        )
        session.add(user)
        await session.flush()
        return user

    user.username = tg_user.username
    user.first_name = tg_user.first_name
    if state:
        user.current_state = state
    return user


async def set_user_state(session: AsyncSession, tg_user: TelegramUser, state: str) -> User:
    return await upsert_user(session, tg_user, state=state)


async def set_user_type(session: AsyncSession, tg_user: TelegramUser, user_type: str) -> User:
    user = await upsert_user(session, tg_user, state=UserState.WAIT_SOURCE)
    user.user_type = user_type
    return user


async def create_project_from_source(
    session: AsyncSession,
    tg_user: TelegramUser,
    source_type: str,
    raw_input: str,
    source_value: str | None = None,
) -> Project:
    user = await upsert_user(session, tg_user, state=UserState.ANALYZING)
    project = Project(
        user_id=user.id,
        source_type=source_type,
        source_value=source_value,
        raw_input=raw_input,
        status="pending_analysis",
    )
    session.add(project)
    await session.flush()
    user.current_project_id = project.id
    return project


async def get_latest_project_for_tg_user(session: AsyncSession, telegram_id: int) -> Project | None:
    return await session.scalar(
        select(Project)
        .join(User, User.id == Project.user_id)
        .where(User.telegram_id == telegram_id)
        .order_by(Project.id.desc())
        .limit(1)
    )


async def get_projects_for_tg_user(session: AsyncSession, telegram_id: int, limit: int = 20) -> list[Project]:
    return list(
        await session.scalars(
            select(Project)
            .join(User, User.id == Project.user_id)
            .options(selectinload(Project.audience_profile))
            .where(User.telegram_id == telegram_id)
            .order_by(Project.id.desc())
            .limit(limit)
        )
    )


async def get_project_for_tg_user(session: AsyncSession, telegram_id: int, project_id: int) -> Project | None:
    return await session.scalar(
        select(Project)
        .join(User, User.id == Project.user_id)
        .options(selectinload(Project.audience_profile))
        .where(User.telegram_id == telegram_id, Project.id == project_id)
        .limit(1)
    )


async def set_current_project_for_tg_user(session: AsyncSession, telegram_id: int, project_id: int) -> Project | None:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        return None

    project = await session.scalar(
        select(Project)
        .options(selectinload(Project.audience_profile))
        .where(Project.id == project_id, Project.user_id == user.id)
        .limit(1)
    )
    if project is None:
        return None

    user.current_project_id = project.id
    return project


async def get_current_project_for_tg_user(session: AsyncSession, telegram_id: int) -> Project | None:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or user.current_project_id is None:
        return None

    return await get_project_for_tg_user(session, telegram_id, user.current_project_id)


async def get_current_ideas(session: AsyncSession, project_id: int, limit: int = 6) -> list[Idea]:
    latest = (
        await session.scalars(
            select(Idea).where(Idea.project_id == project_id).order_by(Idea.id.desc()).limit(limit)
        )
    ).all()
    return sorted(latest, key=lambda idea: idea.id)
