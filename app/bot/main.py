import asyncio
import logging

from app.core.config import settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    if not settings.bot_token:
        logger.warning("BOT_TOKEN is empty; bot polling is disabled")
        while True:
            await asyncio.sleep(3600)

    logger.info("Bot entrypoint is ready; handlers will be wired in later phases")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
