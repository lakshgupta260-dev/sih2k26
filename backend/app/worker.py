"""Celery application shared by dispatchers and workers.

``include`` is the list of modules a **worker** process imports on startup, and
it is the only thing that registers tasks with that worker. It listed just
``app.tasks.document_tasks``, so a worker came up knowing one task out of four.

That was latent rather than broken -- ``process_uploaded_file`` is currently
the only task anything dispatches with ``.delay()`` -- but it fails the moment
that changes, and ``app/tasks/prediction_tasks.py`` says in its own docstring
that fitting a forest and scoring a schedule are "worth moving off the request
path", so it is a change somebody is going to make.

Reproduced against a live worker before this was fixed:

    >>> train_delay_model.delay(project_id, actor_id)
    state: FAILURE
    NotRegistered 'prediction.train_delay_model'

and in that worker's log:

    ERROR/MainProcess Received unregistered task of type
    'prediction.train_delay_model'.  KeyError: 'prediction.train_delay_model'

The broker accepts and acknowledges the message, so the caller gets a task id
back and nothing ever runs it -- a silent drop rather than a loud failure,
which is the hard kind to notice in production.

``tests/test_worker_registration.py`` asserts that every module under
``app.tasks`` appears in ``TASK_MODULES``, so a task module added in a later
phase cannot be forgotten the same way.
"""
from celery import Celery

from app.core.config import settings

# Every module that defines a task. A module missing here means a worker
# silently drops that task -- see the module docstring.
TASK_MODULES = [
    "app.tasks.document_tasks",
    "app.tasks.matching_tasks",
    "app.tasks.prediction_tasks",
]

celery_app = Celery(
    "sih26122",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=TASK_MODULES,
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
