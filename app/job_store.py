import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from app.models import JobState


class ActiveJobError(RuntimeError):
    """Raised when a new job is requested while another is active."""


@dataclass
class JobRecord:
    id: UUID
    state: JobState
    progress: int
    message: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    output_path: Path | None = None


class JobStore:
    def __init__(self, output_dir: Path, retention_seconds: int = 3600) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.retention_seconds = retention_seconds
        self._jobs: dict[UUID, JobRecord] = {}
        self._active_job_id: UUID | None = None
        self._lock = asyncio.Lock()

    async def create(self) -> JobRecord:
        async with self._lock:
            if self._active_job_id is not None:
                raise ActiveJobError("已有任务正在生成")
            now = datetime.now(UTC)
            record = JobRecord(
                id=uuid4(),
                state=JobState.QUEUED,
                progress=0,
                message="等待生成",
                created_at=now,
                updated_at=now,
            )
            self._jobs[record.id] = record
            self._active_job_id = record.id
            return replace(record)

    async def get(self, job_id: UUID) -> JobRecord | None:
        async with self._lock:
            record = self._jobs.get(job_id)
            return replace(record) if record is not None else None

    async def start(self, job_id: UUID) -> None:
        async with self._lock:
            record = self._require(job_id)
            record.state = JobState.RUNNING
            record.message = "正在连接语音服务"
            record.updated_at = datetime.now(UTC)

    async def update_progress(
        self, job_id: UUID, progress: int, message: str
    ) -> None:
        async with self._lock:
            record = self._require(job_id)
            if record.state is not JobState.RUNNING:
                return
            record.progress = max(record.progress, min(95, progress))
            record.message = message
            record.updated_at = datetime.now(UTC)

    async def complete(self, job_id: UUID, output_path: Path) -> None:
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise ValueError("生成的音频文件为空")
        async with self._lock:
            record = self._require(job_id)
            record.state = JobState.COMPLETED
            record.progress = 100
            record.message = "生成完成"
            record.output_path = output_path
            record.updated_at = datetime.now(UTC)
            self._release(job_id)

    async def fail(self, job_id: UUID, public_error: str) -> None:
        async with self._lock:
            record = self._require(job_id)
            record.state = JobState.FAILED
            record.message = "生成失败"
            record.error = public_error
            record.updated_at = datetime.now(UTC)
            self._release(job_id)

    async def cleanup_expired(self, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now(UTC)) - timedelta(
            seconds=self.retention_seconds
        )
        async with self._lock:
            expired = [
                record
                for record in self._jobs.values()
                if record.state in {JobState.COMPLETED, JobState.FAILED}
                and record.updated_at < cutoff
            ]
            root = self.output_dir.resolve()
            for record in expired:
                if record.output_path is not None:
                    candidate = record.output_path.resolve()
                    if candidate.is_relative_to(root) and candidate.is_file():
                        candidate.unlink()
                self._jobs.pop(record.id, None)
            return len(expired)

    def _require(self, job_id: UUID) -> JobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"unknown job: {job_id}") from exc

    def _release(self, job_id: UUID) -> None:
        if self._active_job_id == job_id:
            self._active_job_id = None
