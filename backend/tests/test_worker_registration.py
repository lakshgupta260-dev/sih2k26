"""Every task module must be registered with the Celery app.

The defect this guards against was found in Phase 11 and confirmed against a
live worker: ``app/worker.py`` listed only ``app.tasks.document_tasks`` in its
``include``, so a worker process started knowing one task out of four. The
broker still accepted and acknowledged a dispatch of any other task, the caller
still received a task id, and nothing ever ran it:

    NotRegistered 'prediction.train_delay_model'

A silent drop is the worst available failure mode -- there is no exception at
the call site and no failed job to notice -- so it is worth a test that cannot
be satisfied by remembering to update a list.

These tests need no broker. Task registration is a property of importing the
modules, which is exactly what the ``include`` list drives.
"""
from __future__ import annotations

import pkgutil

import app.tasks
from app.worker import TASK_MODULES, celery_app


def _discovered_task_modules() -> set[str]:
    """Every module under ``app.tasks``, found by walking the package.

    Discovery rather than a hardcoded list is the point: a task module added in
    a later phase is picked up here automatically and fails the test below
    until it is registered.
    """
    return {
        module.name
        for module in pkgutil.iter_modules(app.tasks.__path__, prefix="app.tasks.")
        if not module.name.rsplit(".", 1)[-1].startswith("_")
    }


def test_every_task_module_is_in_the_include_list() -> None:
    discovered = _discovered_task_modules()
    missing = discovered - set(TASK_MODULES)

    assert not missing, (
        f"task module(s) {sorted(missing)} are not in app.worker.TASK_MODULES. "
        "A worker will not register their tasks, and dispatching one will be "
        "acknowledged by the broker and then silently dropped."
    )


def test_the_include_list_has_no_stale_entries() -> None:
    """A module that no longer exists would make the worker fail to boot."""
    stale = set(TASK_MODULES) - _discovered_task_modules()
    assert not stale, f"app.worker.TASK_MODULES references missing module(s): {sorted(stale)}"


def test_the_known_task_names_are_registered_on_the_app() -> None:
    """Assert the task *names*, which are what a dispatch actually carries.

    A module can be imported and still fail to register under the expected name
    if its ``@celery_app.task(name=...)`` is changed, and the mismatch would
    only show up as a NotRegistered at runtime.
    """
    # Importing the app is not enough; the include list is consumed by workers,
    # so import the modules the way a worker does.
    for module in TASK_MODULES:
        __import__(module)

    expected = {
        "documents.process_uploaded_file",
        "matching.run_project_matching",
        "prediction.train_delay_model",
        "prediction.predict_schedule",
    }
    registered = set(celery_app.tasks.keys())

    missing = expected - registered
    assert not missing, f"task name(s) not registered: {sorted(missing)}"


def test_no_task_module_is_missing_from_discovery() -> None:
    """Sanity check on the discovery helper itself.

    If ``iter_modules`` returned nothing, both tests above would pass while
    checking nothing at all.
    """
    discovered = _discovered_task_modules()
    assert len(discovered) >= 3, f"discovery looks broken, found: {discovered}"
