import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import aiohttp

from app.config import AzureSpeechConfig
from app.tts_service import (
    AudioWriteError,
    EmptyAudioError,
    ProgressCallback,
    TTSAuthenticationError,
    TTSQuotaError,
    TTSServiceError,
    TTSUnavailableError,
)


SSML_NAMESPACE = "http://www.w3.org/2001/10/synthesis"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"


class AzureTTSService:
    def __init__(
        self,
        config: AzureSpeechConfig,
        session_factory: Callable[..., Any] = aiohttp.ClientSession,
    ) -> None:
        self._config = config
        self._session_factory = session_factory

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: int,
        pitch: int,
        volume: int,
        output_path: Path,
        on_progress: ProgressCallback,
    ) -> None:
        if not self._config.configured:
            raise TTSUnavailableError("Azure Speech is not configured")

        part_path = output_path.with_suffix(f"{output_path.suffix}.part")
        try:
            await on_progress(10, "正在连接 Azure")
            timeout = aiohttp.ClientTimeout(total=120)
            async with self._session_factory(timeout=timeout) as session:
                async with session.post(
                    self._endpoint(),
                    headers=self._headers(),
                    data=self._build_ssml(text, voice, rate, pitch, volume),
                ) as response:
                    self._raise_for_status(response.status)
                    await on_progress(70, "正在合成语音")
                    audio = await response.read()

            if not audio:
                raise EmptyAudioError("Azure Speech returned no audio")

            await on_progress(90, "正在保存音频")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            part_path.write_bytes(audio)
            if part_path.stat().st_size == 0:
                raise EmptyAudioError("Azure Speech returned no audio")
            part_path.replace(output_path)
        except asyncio.CancelledError:
            self._remove_partial(part_path)
            raise
        except EmptyAudioError:
            self._remove_partial(part_path)
            raise
        except (aiohttp.ClientError, ConnectionError, TimeoutError) as exc:
            self._remove_partial(part_path)
            raise TTSUnavailableError("Unable to connect to Azure Speech") from exc
        except OSError as exc:
            self._remove_partial(part_path)
            raise AudioWriteError("Unable to write Azure audio") from exc

    def _endpoint(self) -> str:
        return (
            f"https://{self._config.region}.tts.speech.microsoft.com/"
            "cognitiveservices/v1"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Ocp-Apim-Subscription-Key": self._config.key or "",
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "voice-studio",
        }

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if status == 200:
            return
        if status in {401, 403}:
            raise TTSAuthenticationError("Azure Speech authentication failed")
        if status == 429:
            raise TTSQuotaError("Azure Speech quota exceeded")
        raise TTSServiceError(f"Azure Speech request failed with status {status}")

    @staticmethod
    def _build_ssml(
        text: str, voice: str, rate: int, pitch: int, volume: int
    ) -> str:
        ElementTree.register_namespace("", SSML_NAMESPACE)
        speak = ElementTree.Element(
            f"{{{SSML_NAMESPACE}}}speak",
            {"version": "1.0", f"{{{XML_NAMESPACE}}}lang": "zh-CN"},
        )
        voice_node = ElementTree.SubElement(speak, "voice", {"name": voice})
        prosody = ElementTree.SubElement(
            voice_node,
            "prosody",
            {
                "rate": f"{rate:+d}%",
                "pitch": f"{pitch:+d}%",
                "volume": f"{volume:+d}%",
            },
        )
        prosody.text = text
        return ElementTree.tostring(speak, encoding="unicode")

    @staticmethod
    def _remove_partial(part_path: Path) -> None:
        try:
            part_path.unlink(missing_ok=True)
        except OSError:
            pass
