from celery import Celery
from app.config import settings

celery = Celery(
    "wamcp",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery.conf.task_routes = {
    "app.workers.tasks.*": {"queue": "default"},
}
