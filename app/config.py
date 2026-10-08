import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class AzureSpeechConfig:
    key: str | None
    region: str | None

    @classmethod
    def from_env(cls) -> "AzureSpeechConfig":
        load_dotenv()
        return cls(
            key=cls._clean(os.getenv("AZURE_SPEECH_KEY")),
            region=cls._clean(os.getenv("AZURE_SPEECH_REGION")),
        )

    @property
    def configured(self) -> bool:
        return self.key is not None and self.region is not None

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
