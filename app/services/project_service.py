import re

from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import UserState
from app.db.models import Project, User

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
    return project
