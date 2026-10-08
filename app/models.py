from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VoiceOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    gender: Literal["男声", "女声"]
    description: str


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    voice: str
    rate: int = Field(default=0, ge=-50, le=50)
    pitch: int = Field(default=0, ge=-50, le=50)
    volume: int = Field(default=0, ge=-50, le=50)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("文本不能为空")
        return normalized


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResponse(BaseModel):
    id: UUID
    state: JobState
    progress: int = Field(ge=0, le=100)
    message: str
    error: str | None = None
    audio_url: str | None = None
