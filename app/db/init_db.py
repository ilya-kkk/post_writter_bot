import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base, Tariff
from app.db.session import engine, session_factory

TARIFFS = [
    {
        "code": "lite",
        "name": "Лайт",
        "projects_limit": 1,
        "posts_limit": 25,
        "monthly_price": 1790,
    },
    {
        "code": "standard",
        "name": "Стандарт",
        "projects_limit": 2,
        "posts_limit": 50,
        "monthly_price": 3190,
    },
]


async def create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_tariffs(session: AsyncSession) -> None:
    for tariff_data in TARIFFS:
        existing = await session.scalar(select(Tariff).where(Tariff.code == tariff_data["code"]))
        if existing:
            existing.name = tariff_data["name"]
            existing.projects_limit = tariff_data["projects_limit"]
            existing.posts_limit = tariff_data["posts_limit"]
            existing.monthly_price = tariff_data["monthly_price"]
            existing.is_active = True
            continue
        session.add(Tariff(**tariff_data, is_active=True))


async def init_db() -> None:
    await create_schema()
    async with session_factory()() as session:
        await seed_tariffs(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(init_db())
