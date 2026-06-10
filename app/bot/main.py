import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from app.bot.handlers import callbacks, ideas, menu, onboarding, payments, start
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.init_db import init_db

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    await init_db()
    if not settings.bot_token:
        logger.warning("BOT_TOKEN is empty; bot polling is disabled")
        while True:
            await asyncio.sleep(3600)

    bot = Bot(settings.bot_token, session=AiohttpSession(timeout=settings.telegram_timeout_seconds))
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать заново"),
            BotCommand(command="menu", description="Меню подписки"),
            BotCommand(command="new", description="Новый проект"),
            BotCommand(command="ideas", description="Идеи для поста"),
            BotCommand(command="status", description="Статус подписки"),
        ]
    )
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage, events_isolation=storage.create_isolation())
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(onboarding.router)
    dp.include_router(callbacks.router)
    dp.include_router(ideas.router)
    dp.include_router(payments.router)

    logger.info("Starting bot polling")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
