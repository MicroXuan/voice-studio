import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import pytest_asyncio

from app.job_store import JobStore
from app.main import create_app
from app.tts_service import (
    AudioWriteError,
    EmptyAudioError,
    TTSAuthenticationError,
    TTSQuotaError,
    TTSServiceError,
    TTSUnavailableError,
)
from app.voices import build_voice_catalog


class ControlledSynthesizer:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.mode: Literal[
            "success",
            "failure",
            "empty",
            "authentication",
            "quota",
            "service",
            "empty_error",
            "write_error",
        ] = "success"
        self.progress_message = "正在生成语音"

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: int,
        pitch: int,
        volume: int,
        output_path: Path,
        on_progress: Callable[[int, str], Awaitable[None]],
    ) -> None:
        await on_progress(42, self.progress_message)
        self.started.set()
        await self.release.wait()
        if self.mode == "failure":
            raise TTSUnavailableError("private upstream detail")
        if self.mode == "authentication":
            raise TTSAuthenticationError("private authentication detail")
        if self.mode == "quota":
            raise TTSQuotaError("private quota detail")
        if self.mode == "service":
            raise TTSServiceError("private service detail")
        if self.mode == "empty_error":
            raise EmptyAudioError("private empty detail")
        if self.mode == "write_error":
            raise AudioWriteError("private path detail")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"" if self.mode == "empty" else b"test-mp3")


@dataclass
class ApiHarness:
    client: httpx.AsyncClient
    store: JobStore
    synthesizer: ControlledSynthesizer


@pytest_asyncio.fixture
async def api_harness(tmp_path: Path) -> AsyncIterator[ApiHarness]:
    store = JobStore(tmp_path / "audio", retention_seconds=3600)
    synthesizer = ControlledSynthesizer()
    app = create_app(
        store=store,
        tts_service=synthesizer,
        catalog=build_voice_catalog(False),
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield ApiHarness(client, store, synthesizer)


@pytest_asyncio.fixture
async def configured_api_harness(tmp_path: Path) -> AsyncIterator[ApiHarness]:
    store = JobStore(tmp_path / "audio", retention_seconds=3600)
    synthesizer = ControlledSynthesizer()
    app = create_app(
        store=store,
        tts_service=synthesizer,
        catalog=build_voice_catalog(True),
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield ApiHarness(client, store, synthesizer)
