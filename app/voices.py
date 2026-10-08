from app.models import VoiceOption


VOICES: tuple[VoiceOption, ...] = (
    VoiceOption(
        id="zh-CN-YunxiNeural",
        name="云希",
        gender="男声",
        description="自然清晰，适合知识讲解与日常旁白",
    ),
    VoiceOption(
        id="zh-CN-YunzeNeural",
        name="云泽",
        gender="男声",
        description="沉稳有力，适合故事、纪录片与长文",
    ),
    VoiceOption(
        id="zh-CN-XiaoxiaoNeural",
        name="晓晓",
        gender="女声",
        description="亲切明亮，适合生活内容与轻松表达",
    ),
)


def get_voice(voice_id: str) -> VoiceOption | None:
    return next((voice for voice in VOICES if voice.id == voice_id), None)
