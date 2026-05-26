"""Lifecycle tests for the asyncio loop wrappers in ``app/domains/files/worker.py``.

These focus on concerns the service-level tests cannot cover:

- The global ``FILE_MAINTENANCE_ENABLED`` flag mutes every worker
  immediately, before the first sleep.
- Each worker honors ``CancelledError`` cleanly so shutdown in
  ``app/main.py`` does not hang or leak warnings.

The actual maintenance logic is verified by ``test_files_maintenance.py``;
duplicating those assertions here would require dropping the savepoint
isolation of the ``db_session`` fixture (the worker uses its own
sessionmaker built from the engine, which cannot see uncommitted data).
"""

import asyncio
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings, get_settings
from app.core.storage import ObjectStorage
from app.domains.files import worker as worker_module
from app.domains.files.worker import (
    run_chat_retention_worker,
    run_pending_cleanup_worker,
    run_physical_purge_worker,
)

settings = get_settings()


class _NeverCalledStorage(ObjectStorage):
    """Storage stub asserting nothing reaches the backend.

    Workers should never hit storage when disabled, and during a fast
    cancellation the cleanup loop must not race a probe through.
    """

    async def generate_presigned_upload(
        self,
        object_key: str,
        content_type: str,
        max_size_bytes: int,
        expires_in_seconds: int,
    ) -> Any:
        raise AssertionError("storage must not be touched in lifecycle tests")

    async def generate_presigned_download_url(
        self, object_key: str, expires_in_seconds: int
    ) -> str:
        raise AssertionError("storage must not be touched in lifecycle tests")

    async def object_exists(self, object_key: str) -> bool:
        raise AssertionError("storage must not be touched in lifecycle tests")

    async def get_object_size(self, object_key: str) -> int | None:
        # The cleanup worker calls this on every stale pending row. We
        # return None so any accidental scan during the cancellation window
        # marks the row failed (no-op since the test DB has no stale rows).
        return None

    async def delete_object(self, object_key: str) -> None:
        raise AssertionError("storage must not be touched in lifecycle tests")


@pytest.fixture
def engine_for_worker() -> AsyncEngine:
    return create_async_engine(settings.test_database_url, echo=False)


@pytest.fixture
def disabled_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``get_settings`` in the worker module with a frozen copy.

    Mutating the cached ``Settings`` instance is unreliable because
    ``@lru_cache`` plus ``cache_clear()`` can be defeated by import-time
    binding in the worker module. Replacing the name the worker actually
    looks up gives us an unambiguous override that auto-restores on
    teardown.
    """
    disabled = Settings(FILE_MAINTENANCE_ENABLED=False)
    monkeypatch.setattr(worker_module, "get_settings", lambda: disabled)


class TestWorkerLoopLifecycle:
    @pytest.mark.asyncio
    async def test_pending_cleanup_worker_is_no_op_when_flag_disabled(
        self,
        engine_for_worker: AsyncEngine,
        disabled_settings: None,
    ) -> None:
        """The worker must return immediately rather than entering the loop."""
        await asyncio.wait_for(
            run_pending_cleanup_worker(engine_for_worker, _NeverCalledStorage()),
            timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_chat_retention_worker_is_no_op_when_flag_disabled(
        self,
        engine_for_worker: AsyncEngine,
        disabled_settings: None,
    ) -> None:
        await asyncio.wait_for(
            run_chat_retention_worker(engine_for_worker, _NeverCalledStorage()),
            timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_physical_purge_worker_is_no_op_when_flag_disabled(
        self,
        engine_for_worker: AsyncEngine,
        disabled_settings: None,
    ) -> None:
        await asyncio.wait_for(
            run_physical_purge_worker(engine_for_worker, _NeverCalledStorage()),
            timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_pending_cleanup_worker_cancels_cleanly(
        self,
        engine_for_worker: AsyncEngine,
    ) -> None:
        """Cancellation mid-loop must surface ``CancelledError`` and nothing else.

        We rely on the default long ``FILE_CLEANUP_PENDING_INTERVAL_SECONDS``
        so the worker is parked in ``asyncio.sleep`` when we cancel; this
        mirrors the real shutdown path in ``app/main.py``.
        """
        task = asyncio.create_task(
            run_pending_cleanup_worker(engine_for_worker, _NeverCalledStorage())
        )
        # Give the loop time to do one tick (no rows to process) and park
        # in the sleep.
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_chat_retention_worker_cancels_cleanly(
        self,
        engine_for_worker: AsyncEngine,
    ) -> None:
        task = asyncio.create_task(
            run_chat_retention_worker(engine_for_worker, _NeverCalledStorage())
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_physical_purge_worker_cancels_cleanly(
        self,
        engine_for_worker: AsyncEngine,
    ) -> None:
        task = asyncio.create_task(
            run_physical_purge_worker(engine_for_worker, _NeverCalledStorage())
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
