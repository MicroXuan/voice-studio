from pathlib import Path
from typing import Any

import pytest

from app.tts_router import TTSRouter
from app.voices import build_voice_catalog


class RecordingSynthesizer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: int,
        pitch: int,
        volume: int,
        output_path: Path,
        on_progress: Any,
    ) -> None:
        self.calls.append(
            {
                "text": text,
                "voice": voice,
                "rate": rate,
                "pitch": pitch,
                "volume": volume,
                "output_path": output_path,
                "on_progress": on_progress,
            }
        )


async def progress_callback(progress: int, message: str) -> None:
    return None


@pytest.mark.asyncio
async def test_router_sends_edge_voice_only_to_edge(tmp_path: Path) -> None:
    edge = RecordingSynthesizer()
    azure = RecordingSynthesizer()
    router = TTSRouter(build_voice_catalog(True), edge, azure)
    output = tmp_path / "edge.mp3"

    await router.synthesize(
        "边缘声音", "zh-CN-YunxiNeural", 10, -5, 2, output, progress_callback
    )

    assert edge.calls == [
        {
            "text": "边缘声音",
            "voice": "zh-CN-YunxiNeural",
            "rate": 10,
            "pitch": -5,
            "volume": 2,
            "output_path": output,
            "on_progress": progress_callback,
        }
    ]
    assert azure.calls == []


@pytest.mark.asyncio
async def test_router_sends_yunze_only_to_azure(tmp_path: Path) -> None:
    edge = RecordingSynthesizer()
    azure = RecordingSynthesizer()
    router = TTSRouter(build_voice_catalog(True), edge, azure)
    output = tmp_path / "azure.mp3"

    await router.synthesize(
        "云泽声音", "zh-CN-YunzeNeural", -3, 7, -1, output, progress_callback
    )

    assert edge.calls == []
    assert azure.calls == [
        {
            "text": "云泽声音",
            "voice": "zh-CN-YunzeNeural",
            "rate": -3,
            "pitch": 7,
            "volume": -1,
            "output_path": output,
            "on_progress": progress_callback,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("voice", ["zh-CN-YunzeNeural", "unknown"])
async def test_router_rejects_unavailable_or_unknown_voice(
    tmp_path: Path, voice: str
) -> None:
    edge = RecordingSynthesizer()
    azure = RecordingSynthesizer()
    router = TTSRouter(build_voice_catalog(False), edge, azure)

    with pytest.raises(ValueError):
        await router.synthesize(
            "测试", voice, 0, 0, 0, tmp_path / "voice.mp3", progress_callback
        )

    assert edge.calls == []
    assert azure.calls == []
