import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from app.job_store import ActiveJobError, JobStore
from app.models import JobState


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "audio", retention_seconds=60)


@pytest.mark.asyncio
async def test_job_moves_queued_running_completed(store: JobStore) -> None:
    job = await store.create()
    assert job.state is JobState.QUEUED
    assert job.progress == 0

    await store.start(job.id)
    running = await store.get(job.id)
    assert running is not None
    assert running.state is JobState.RUNNING

    output = store.output_dir / f"{job.id}.mp3"
    output.write_bytes(b"audio")
    await store.complete(job.id, output)

    completed = await store.get(job.id)
    assert completed is not None
    assert completed.state is JobState.COMPLETED
    assert completed.progress == 100
    assert completed.output_path == output


@pytest.mark.asyncio
async def test_progress_never_moves_backwards_or_above_95_while_running(
    store: JobStore,
) -> None:
    job = await store.create()
    await store.start(job.id)

    await store.update_progress(job.id, 72, "正在生成")
    await store.update_progress(job.id, 30, "较旧进度")
    await store.update_progress(job.id, 100, "仍在生成")

    current = await store.get(job.id)
    assert current is not None
    assert current.progress == 95
    assert current.message == "仍在生成"


@pytest.mark.asyncio
async def test_only_one_active_job_can_be_created(store: JobStore) -> None:
    await store.create()

    with pytest.raises(ActiveJobError):
        await store.create()


@pytest.mark.asyncio
async def test_concurrent_create_allows_exactly_one_job(store: JobStore) -> None:
    results = await asyncio.gather(
        store.create(), store.create(), return_exceptions=True
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ActiveJobError) for result in results) == 1


@pytest.mark.asyncio
async def test_failed_job_releases_active_slot(store: JobStore) -> None:
    first = await store.create()
    await store.start(first.id)
    await store.fail(first.id, "网络不可用")

    failed = await store.get(first.id)
    assert failed is not None
    assert failed.state is JobState.FAILED
    assert failed.error == "网络不可用"

    second = await store.create()
    assert second.id != first.id


@pytest.mark.asyncio
async def test_cleanup_removes_expired_record_and_owned_audio(
    store: JobStore,
) -> None:
    job = await store.create()
    await store.start(job.id)
    output = store.output_dir / f"{job.id}.mp3"
    output.write_bytes(b"audio")
    await store.complete(job.id, output)
    completed = await store.get(job.id)
    assert completed is not None

    removed = await store.cleanup_expired(
        now=completed.updated_at + timedelta(seconds=61)
    )

    assert removed == 1
    assert await store.get(job.id) is None
    assert not output.exists()


@pytest.mark.asyncio
async def test_cleanup_does_not_delete_file_outside_output_dir(
    store: JobStore, tmp_path: Path
) -> None:
    job = await store.create()
    await store.start(job.id)
    external = tmp_path / "keep.mp3"
    external.write_bytes(b"audio")
    await store.complete(job.id, external)
    completed = await store.get(job.id)
    assert completed is not None

    removed = await store.cleanup_expired(
        now=completed.updated_at + timedelta(seconds=61)
    )

    assert removed == 1
    assert external.exists()
