import asyncio
import logging

from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    logger.info("Scheduler entrypoint is ready; jobs will be wired in later phases")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
