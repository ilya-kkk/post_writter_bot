import logging

from redis import Redis
from rq import Queue, Worker

from app.core.config import settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    redis = Redis.from_url(settings.redis_url)
    queue = Queue("default", connection=redis)
    logger.info("Starting RQ worker for queue: %s", queue.name)
    Worker([queue], connection=redis).work()


if __name__ == "__main__":
    main()
