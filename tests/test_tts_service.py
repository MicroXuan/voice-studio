import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from app.tts_service import (
    AudioWriteError,
    EdgeTTSService,
    EmptyAudioError,
    TTSUnavailableError,
)


class FakeCommunicate:
    def __init__(self, events: list[dict[str, Any]], failure: Exception | None = None):
        self.events = events
        self.failure = failure

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        for event in self.events:
            yield event
        if self.failure is not None:
            raise self.failure


class CapturingFactory:
    def __init__(
        self, events: list[dict[str, Any]], failure: Exception | None = None
    ) -> None:
        self.events = events
        self.failure = failure
        self.calls: list[dict[str, Any]] = []

    def __call__(self, text: str, voice: str, **kwargs: Any) -> FakeCommunicate:
        self.calls.append({"text": text, "voice": voice, **kwargs})
        return FakeCommunicate(self.events, self.failure)


async def record_progress(values: list[int], progress: int) -> None:
    values.append(progress)


@pytest.mark.asyncio
async def test_formats_controls_with_explicit_sign(tmp_path: Path) -> None:
    factory = CapturingFactory([{"type": "audio", "data": b"mp3"}])
    service = EdgeTTSService(factory)

    await service.synthesize(
        "测试",
        "zh-CN-YunxiNeural",
        rate=0,
        pitch=12,
        volume=-8,
        output_path=tmp_path / "voice.mp3",
        on_progress=lambda value: record_progress([], value),
    )

    assert factory.calls == [
        {
            "text": "测试",
            "voice": "zh-CN-YunxiNeural",
            "rate": "+0%",
            "pitch": "+12Hz",
            "volume": "-8%",
        }
    ]


@pytest.mark.asyncio
async def test_writes_audio_chunks_to_final_mp3(tmp_path: Path) -> None:
    factory = CapturingFactory(
        [
            {"type": "audio", "data": b"first"},
            {"type": "audio", "data": b"second"},
        ]
    )
    service = EdgeTTSService(factory)
    output = tmp_path / "voice.mp3"

    await service.synthesize(
        "测试",
        "zh-CN-YunxiNeural",
        0,
        0,
        0,
        output,
        lambda value: record_progress([], value),
    )

    assert output.read_bytes() == b"firstsecond"
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_boundary_progress_is_monotonic_and_capped_at_95(
    tmp_path: Path,
) -> None:
    factory = CapturingFactory(
        [
            {"type": "WordBoundary", "text": "甲乙"},
            {"type": "WordBoundary", "text": "丙"},
            {"type": "WordBoundary", "text": "丁戊"},
            {"type": "audio", "data": b"mp3"},
        ]
    )
    service = EdgeTTSService(factory)
    progress_values: list[int] = []

    await service.synthesize(
        "甲乙丙丁",
        "zh-CN-YunxiNeural",
        0,
        0,
        0,
        tmp_path / "voice.mp3",
        lambda value: record_progress(progress_values, value),
    )

    assert progress_values == [47, 71, 95]
    assert progress_values == sorted(progress_values)


@pytest.mark.asyncio
async def test_sentence_boundary_updates_progress_for_current_edge_stream(
    tmp_path: Path,
) -> None:
    factory = CapturingFactory(
        [
            {"type": "SentenceBoundary", "text": "第一句。"},
            {"type": "SentenceBoundary", "text": "第二句。"},
            {"type": "audio", "data": b"mp3"},
        ]
    )
    service = EdgeTTSService(factory)
    progress_values: list[int] = []

    await service.synthesize(
        "第一句。第二句。",
        "zh-CN-YunxiNeural",
        0,
        0,
        0,
        tmp_path / "voice.mp3",
        lambda value: record_progress(progress_values, value),
    )

    assert progress_values == [47, 95]


@pytest.mark.asyncio
async def test_no_audio_raises_empty_audio_and_removes_partial_file(
    tmp_path: Path,
) -> None:
    factory = CapturingFactory([{"type": "WordBoundary", "text": "测试"}])
    service = EdgeTTSService(factory)
    output = tmp_path / "voice.mp3"

    with pytest.raises(EmptyAudioError):
        await service.synthesize(
            "测试",
            "zh-CN-YunxiNeural",
            0,
            0,
            0,
            output,
            lambda value: record_progress([], value),
        )

    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_network_exception_becomes_tts_unavailable(tmp_path: Path) -> None:
    factory = CapturingFactory([], aiohttp.ClientConnectionError("private detail"))
    service = EdgeTTSService(factory)
    output = tmp_path / "voice.mp3"

    with pytest.raises(TTSUnavailableError):
        await service.synthesize(
            "测试",
            "zh-CN-YunxiNeural",
            0,
            0,
            0,
            output,
            lambda value: record_progress([], value),
        )

    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_write_exception_becomes_audio_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = CapturingFactory([{"type": "audio", "data": b"mp3"}])
    service = EdgeTTSService(factory)
    output = tmp_path / "voice.mp3"

    def deny_write(path: Path, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError("private path detail")

    monkeypatch.setattr(Path, "open", deny_write)

    with pytest.raises(AudioWriteError):
        await service.synthesize(
            "测试",
            "zh-CN-YunxiNeural",
            0,
            0,
            0,
            output,
            lambda value: record_progress([], value),
        )

    assert not output.exists()


@pytest.mark.asyncio
async def test_cancellation_removes_partial_audio(tmp_path: Path) -> None:
    stream_started = asyncio.Event()
    never_release = asyncio.Event()

    class BlockingCommunicate:
        async def stream(self) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "audio", "data": b"partial"}
            stream_started.set()
            await never_release.wait()

    service = EdgeTTSService(lambda *args, **kwargs: BlockingCommunicate())
    output = tmp_path / "voice.mp3"
    task = asyncio.create_task(
        service.synthesize(
            "测试",
            "zh-CN-YunxiNeural",
            0,
            0,
            0,
            output,
            lambda value: record_progress([], value),
        )
    )
    await asyncio.wait_for(stream_started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()
