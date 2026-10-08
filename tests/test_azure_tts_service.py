import asyncio
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import aiohttp
import pytest

from app.azure_tts_service import AzureTTSService
from app.config import AzureSpeechConfig
from app.tts_service import AudioWriteError, EmptyAudioError, TTSUnavailableError


class FakeResponse:
    def __init__(self, body: bytes = b"azure-mp3", status: int = 200) -> None:
        self.body = body
        self.status = status

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def read(self) -> bytes:
        return self.body


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


class SessionFactory:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.session = FakeSession(response or FakeResponse())

    def __call__(self, **kwargs: Any) -> FakeSession:
        return self.session


class FailingSession(FakeSession):
    def __init__(self, failure: Exception) -> None:
        super().__init__(FakeResponse())
        self.failure = failure

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        raise self.failure


class FailingSessionFactory:
    def __init__(self, failure: Exception) -> None:
        self.session = FailingSession(failure)

    def __call__(self, **kwargs: Any) -> FailingSession:
        return self.session


def configured_service(
    factory: SessionFactory,
) -> AzureTTSService:
    return AzureTTSService(
        AzureSpeechConfig(key="secret-test-key", region="eastasia"),
        session_factory=factory,
    )


@pytest.mark.asyncio
async def test_azure_posts_escaped_ssml_to_regional_endpoint(tmp_path: Path) -> None:
    factory = SessionFactory()
    service = configured_service(factory)

    await service.synthesize(
        '甲 & 乙 < 丙 > 丁 "引号"。',
        "zh-CN-YunzeNeural",
        rate=12,
        pitch=-8,
        volume=0,
        output_path=tmp_path / "voice.mp3",
        on_progress=lambda progress, message: _record_progress([], progress, message),
    )

    assert len(factory.session.calls) == 1
    call = factory.session.calls[0]
    assert call["url"] == (
        "https://eastasia.tts.speech.microsoft.com/cognitiveservices/v1"
    )
    assert call["headers"] == {
        "Ocp-Apim-Subscription-Key": "secret-test-key",
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "voice-studio",
    }
    raw_ssml = call["data"]
    assert "&amp;" in raw_ssml
    assert "&lt;" in raw_ssml
    root = ElementTree.fromstring(raw_ssml)
    voice = root.find("{http://www.w3.org/2001/10/synthesis}voice")
    prosody = voice.find("{http://www.w3.org/2001/10/synthesis}prosody")
    assert voice.attrib["name"] == "zh-CN-YunzeNeural"
    assert prosody.attrib == {"rate": "+12%", "pitch": "-8%", "volume": "+0%"}
    assert prosody.text == '甲 & 乙 < 丙 > 丁 "引号"。'


@pytest.mark.asyncio
async def test_azure_writes_nonempty_mp3_atomically(tmp_path: Path) -> None:
    service = configured_service(SessionFactory(FakeResponse(b"first-second")))
    output = tmp_path / "voice.mp3"

    await service.synthesize(
        "测试",
        "zh-CN-YunzeNeural",
        0,
        0,
        0,
        output,
        lambda progress, message: _record_progress([], progress, message),
    )

    assert output.read_bytes() == b"first-second"
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_azure_reports_stage_progress(tmp_path: Path) -> None:
    service = configured_service(SessionFactory())
    progress_values: list[tuple[int, str]] = []

    await service.synthesize(
        "测试",
        "zh-CN-YunzeNeural",
        0,
        0,
        0,
        tmp_path / "voice.mp3",
        lambda progress, message: _record_progress(
            progress_values, progress, message
        ),
    )

    assert progress_values == [
        (10, "正在连接 Azure"),
        (70, "正在合成语音"),
        (90, "正在保存音频"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (401, "TTSAuthenticationError"),
        (403, "TTSAuthenticationError"),
        (429, "TTSQuotaError"),
        (400, "TTSServiceError"),
        (500, "TTSServiceError"),
    ],
)
async def test_azure_maps_http_status_without_leaking_upstream_body(
    tmp_path: Path, status: int, expected_error: str
) -> None:
    factory = SessionFactory(
        FakeResponse(b"private upstream body secret-test-key", status=status)
    )
    service = configured_service(factory)
    output = tmp_path / "voice.mp3"

    with pytest.raises(RuntimeError) as captured:
        await service.synthesize(
            "测试",
            "zh-CN-YunzeNeural",
            0,
            0,
            0,
            output,
            lambda progress, message: _record_progress([], progress, message),
        )

    assert type(captured.value).__name__ == expected_error
    assert "private upstream body" not in str(captured.value)
    assert "secret-test-key" not in str(captured.value)
    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_azure_network_failure_becomes_unavailable(tmp_path: Path) -> None:
    service = AzureTTSService(
        AzureSpeechConfig(key="secret-test-key", region="eastasia"),
        session_factory=FailingSessionFactory(
            aiohttp.ClientConnectionError("private network detail")
        ),
    )
    output = tmp_path / "voice.mp3"

    with pytest.raises(TTSUnavailableError):
        await service.synthesize(
            "测试",
            "zh-CN-YunzeNeural",
            0,
            0,
            0,
            output,
            lambda progress, message: _record_progress([], progress, message),
        )

    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_azure_empty_success_raises_and_cleans_partial(tmp_path: Path) -> None:
    service = configured_service(SessionFactory(FakeResponse(b"", status=200)))
    output = tmp_path / "voice.mp3"

    with pytest.raises(EmptyAudioError):
        await service.synthesize(
            "测试",
            "zh-CN-YunzeNeural",
            0,
            0,
            0,
            output,
            lambda progress, message: _record_progress([], progress, message),
        )

    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_azure_write_failure_becomes_audio_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = configured_service(SessionFactory())
    output = tmp_path / "voice.mp3"

    def deny_write(path: Path, data: bytes) -> int:
        raise PermissionError("private path detail")

    monkeypatch.setattr(Path, "write_bytes", deny_write)

    with pytest.raises(AudioWriteError):
        await service.synthesize(
            "测试",
            "zh-CN-YunzeNeural",
            0,
            0,
            0,
            output,
            lambda progress, message: _record_progress([], progress, message),
        )

    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()


@pytest.mark.asyncio
async def test_azure_cancellation_cleans_partial(tmp_path: Path) -> None:
    read_started = asyncio.Event()
    never_release = asyncio.Event()

    class BlockingResponse(FakeResponse):
        async def read(self) -> bytes:
            read_started.set()
            await never_release.wait()
            return b"unreachable"

    service = configured_service(SessionFactory(BlockingResponse()))
    output = tmp_path / "voice.mp3"
    task = asyncio.create_task(
        service.synthesize(
            "测试",
            "zh-CN-YunzeNeural",
            0,
            0,
            0,
            output,
            lambda progress, message: _record_progress([], progress, message),
        )
    )
    await asyncio.wait_for(read_started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not output.exists()
    assert not (tmp_path / "voice.mp3.part").exists()


async def _record_progress(
    values: list[tuple[int, str]], progress: int, message: str
) -> None:
    values.append((progress, message))
