from celery import Celery

from app.config import settings

celery_app = Celery(
    "youtoframe",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)
