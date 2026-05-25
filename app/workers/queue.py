from redis import Redis
from rq import Queue

from app.core.config import settings
from app.workers import jobs


def get_queue() -> Queue:
    redis = Redis.from_url(settings.redis_url)
    return Queue("default", connection=redis)


def enqueue_analyze_project(project_id: int, chat_id: int, progress_message_id: int) -> None:
    get_queue().enqueue(jobs.analyze_project_job, project_id, chat_id, progress_message_id)


def enqueue_generate_ideas(project_id: int, chat_id: int, progress_message_id: int) -> None:
    get_queue().enqueue(jobs.generate_ideas_job, project_id, chat_id, progress_message_id)


def enqueue_generate_post(project_id: int, idea_id: int, chat_id: int, progress_message_id: int) -> None:
    get_queue().enqueue(jobs.generate_post_job, project_id, idea_id, chat_id, progress_message_id)
