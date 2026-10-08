from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aiohttp
import edge_tts
from edge_tts.exceptions import EdgeTTSException, NoAudioReceived


class TTSUnavailableError(RuntimeError):
    """Raised when the remote speech service cannot be reached."""


class EmptyAudioError(RuntimeError):
    """Raised when synthesis finishes without audio data."""


class AudioWriteError(RuntimeError):
    """Raised when generated audio cannot be stored locally."""


class EdgeTTSService:
    def __init__(
        self, communicate_factory: Callable[..., Any] = edge_tts.Communicate
    ) -> None:
        self._communicate_factory = communicate_factory

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: int,
        pitch: int,
        volume: int,
        output_path: Path,
        on_progress: Callable[[int], Awaitable[None]],
    ) -> None:
        part_path = output_path.with_suffix(f"{output_path.suffix}.part")
        spoken_chars = 0
        last_progress = 0
        audio_received = False

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            communicator = self._communicate_factory(
                text,
                voice,
                rate=self._format_control(rate, "%"),
                pitch=self._format_control(pitch, "Hz"),
                volume=self._format_control(volume, "%"),
            )
            with part_path.open("wb") as audio_file:
                async for event in communicator.stream():
                    if event["type"] == "audio":
                        audio_file.write(event["data"])
                        audio_received = True
                    elif event["type"] == "WordBoundary":
                        spoken_chars += len(event.get("text", ""))
                        progress = min(95, int(spoken_chars / len(text) * 95))
                        if progress > last_progress:
                            last_progress = progress
                            await on_progress(progress)

            if not audio_received or part_path.stat().st_size == 0:
                raise EmptyAudioError("语音服务没有返回音频")
            part_path.replace(output_path)
        except EmptyAudioError:
            self._remove_partial(part_path)
            raise
        except NoAudioReceived as exc:
            self._remove_partial(part_path)
            raise EmptyAudioError("语音服务没有返回音频") from exc
        except (aiohttp.ClientError, ConnectionError, TimeoutError, EdgeTTSException) as exc:
            self._remove_partial(part_path)
            raise TTSUnavailableError("无法连接语音服务") from exc
        except OSError as exc:
            self._remove_partial(part_path)
            raise AudioWriteError("无法写入音频文件") from exc

    @staticmethod
    def _format_control(value: int, unit: str) -> str:
        return f"{value:+d}{unit}"

    @staticmethod
    def _remove_partial(part_path: Path) -> None:
        try:
            part_path.unlink(missing_ok=True)
        except OSError:
            pass
