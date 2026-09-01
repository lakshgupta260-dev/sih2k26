"""Celery application shared by dispatchers and workers."""
from celery import Celery
from app.core.config import settings
celery_app = Celery("sih26122", broker=settings.celery_broker, backend=settings.celery_backend, include=["app.tasks.document_tasks"])
celery_app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC", enable_utc=True)
