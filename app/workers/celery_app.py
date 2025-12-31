from celery import Celery
from app.config import settings

celery = Celery(
    "wamcp",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery.conf.task_routes = {
    "app.workers.tasks.*": {"queue": "celery"},
}

celery.conf.task_default_queue = "celery"
celery.conf.task_default_exchange = "celery"
celery.conf.task_default_routing_key = "celery"

# Autodiscover tasks from app.workers.tasks module
celery.conf.imports = ("app.workers.tasks",)
