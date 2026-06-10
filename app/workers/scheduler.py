import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.db.session import session_factory
from app.services.followup_service import get_due_followups, send_followup_event

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    await init_db()
    if not settings.bot_token:
        logger.warning("BOT_TOKEN is empty; followup scheduler sending is disabled")
        while True:
            await asyncio.sleep(3600)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(process_followups, "interval", seconds=30, max_instances=1)
    scheduler.start()
    logger.info("Followup scheduler started")
    while True:
        await asyncio.sleep(3600)


async def process_followups() -> None:
    bot = Bot(settings.bot_token, session=AiohttpSession(timeout=settings.telegram_timeout_seconds))
    try:
        async with session_factory()() as session:
            events = await get_due_followups(session)
            if not events:
                return
            for event in events:
                await send_followup_event(session, bot, event)
            await session.commit()
            logger.info("Processed %s followup events", len(events))
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
