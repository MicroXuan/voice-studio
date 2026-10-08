from pathlib import Path

from app.models import VoiceOption
from app.tts_service import ProgressCallback, SpeechSynthesizer
from app.voices import get_voice


class TTSRouter:
    def __init__(
        self,
        catalog: tuple[VoiceOption, ...],
        edge_service: SpeechSynthesizer,
        azure_service: SpeechSynthesizer | None,
    ) -> None:
        self._catalog = catalog
        self._edge_service = edge_service
        self._azure_service = azure_service

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
        option = get_voice(voice, self._catalog)
        if option is None:
            raise ValueError("未知声音")
        if not option.available:
            raise ValueError(option.unavailable_reason or "声音当前不可用")

        service = (
            self._azure_service if option.provider == "azure" else self._edge_service
        )
        if service is None:
            raise ValueError("需配置 Azure Speech")

        await service.synthesize(
            text,
            voice,
            rate,
            pitch,
            volume,
            output_path,
            on_progress,
        )
