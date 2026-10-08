from app.models import VoiceOption


VOICES: tuple[VoiceOption, ...] = (
    VoiceOption(
        id="zh-CN-YunjianNeural",
        name="云健",
        gender="男声",
        description="激情有力，适合体育、故事与有气势的旁白",
    ),
    VoiceOption(
        id="zh-CN-YunxiNeural",
        name="云希",
        gender="男声",
        description="自然清晰，适合知识讲解与日常旁白",
    ),
    VoiceOption(
        id="zh-CN-YunxiaNeural",
        name="云夏",
        gender="男声",
        description="年轻可爱，适合动漫、小说与轻松内容",
    ),
    VoiceOption(
        id="zh-CN-YunyangNeural",
        name="云扬",
        gender="男声",
        description="专业可靠，适合新闻、说明与正式旁白",
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
