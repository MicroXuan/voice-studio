from app.models import VoiceOption


_VOICE_DEFINITIONS = (
    {
        "id": "zh-CN-YunjianNeural",
        "name": "云健",
        "gender": "男声",
        "description": "激情有力，适合体育、故事与有气势的旁白",
        "provider": "edge",
    },
    {
        "id": "zh-CN-YunxiNeural",
        "name": "云希",
        "gender": "男声",
        "description": "自然清晰，适合知识讲解与日常旁白",
        "provider": "edge",
    },
    {
        "id": "zh-CN-YunxiaNeural",
        "name": "云夏",
        "gender": "男声",
        "description": "年轻可爱，适合动漫、小说与轻松内容",
        "provider": "edge",
    },
    {
        "id": "zh-CN-YunyangNeural",
        "name": "云扬",
        "gender": "男声",
        "description": "专业可靠，适合新闻、说明与正式旁白",
        "provider": "edge",
    },
    {
        "id": "zh-CN-YunzeNeural",
        "name": "云泽",
        "gender": "男声",
        "description": "沉稳磁性，适合纪录片、历史与深度旁白",
        "provider": "azure",
    },
    {
        "id": "zh-CN-XiaoxiaoNeural",
        "name": "晓晓",
        "gender": "女声",
        "description": "亲切明亮，适合生活内容与轻松表达",
        "provider": "edge",
    },
)


def build_voice_catalog(azure_configured: bool) -> tuple[VoiceOption, ...]:
    voices: list[VoiceOption] = []
    for definition in _VOICE_DEFINITIONS:
        is_azure = definition["provider"] == "azure"
        available = not is_azure or azure_configured
        voices.append(
            VoiceOption(
                **definition,
                available=available,
                unavailable_reason=None if available else "需配置 Azure Speech",
            )
        )
    return tuple(voices)


VOICES = build_voice_catalog(azure_configured=False)


def get_voice(
    voice_id: str, catalog: tuple[VoiceOption, ...] = VOICES
) -> VoiceOption | None:
    return next((voice for voice in catalog if voice.id == voice_id), None)
