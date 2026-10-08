import pytest

from app.models import SynthesisRequest
from app.voices import VOICES, get_voice


def test_whitespace_text_is_rejected() -> None:
    with pytest.raises(ValueError):
        SynthesisRequest(text=" \n\t ", voice="zh-CN-YunxiNeural")


def test_text_over_20000_characters_is_rejected() -> None:
    with pytest.raises(ValueError):
        SynthesisRequest(text="声" * 20_001, voice="zh-CN-YunxiNeural")


def test_controls_accept_minus_50_and_50() -> None:
    lower = SynthesisRequest(
        text="测试",
        voice="zh-CN-YunxiNeural",
        rate=-50,
        pitch=-50,
        volume=-50,
    )
    upper = SynthesisRequest(
        text="测试",
        voice="zh-CN-YunxiNeural",
        rate=50,
        pitch=50,
        volume=50,
    )

    assert (lower.rate, lower.pitch, lower.volume) == (-50, -50, -50)
    assert (upper.rate, upper.pitch, upper.volume) == (50, 50, 50)


@pytest.mark.parametrize("field", ["rate", "pitch", "volume"])
@pytest.mark.parametrize("value", [-51, 51])
def test_controls_reject_out_of_range_values(field: str, value: int) -> None:
    payload = {"text": "测试", "voice": "zh-CN-YunxiNeural", field: value}

    with pytest.raises(ValueError):
        SynthesisRequest(**payload)


def test_voice_catalog_contains_only_supported_featured_voices() -> None:
    voice_ids = [voice.id for voice in VOICES]

    assert "zh-CN-YunxiNeural" in voice_ids
    assert "zh-CN-YunyangNeural" in voice_ids
    assert "zh-CN-XiaoxiaoNeural" in voice_ids
    assert "zh-CN-YunzeNeural" not in voice_ids
    assert len(voice_ids) == len(set(voice_ids))
    assert get_voice("zh-CN-XiaoxiaoNeural").gender == "女声"
    assert get_voice("zh-CN-UnknownNeural") is None
