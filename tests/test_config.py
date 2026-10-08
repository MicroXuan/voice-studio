import pytest

from app.config import AzureSpeechConfig


@pytest.mark.parametrize(
    ("key", "region", "expected"),
    [
        (None, None, False),
        ("", "eastasia", False),
        ("test-key", "", False),
        ("test-key", "eastasia", True),
    ],
)
def test_config_requires_both_key_and_region(
    monkeypatch: pytest.MonkeyPatch,
    key: str | None,
    region: str | None,
    expected: bool,
) -> None:
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    if key is not None:
        monkeypatch.setenv("AZURE_SPEECH_KEY", key)
    if region is not None:
        monkeypatch.setenv("AZURE_SPEECH_REGION", region)

    assert AzureSpeechConfig.from_env().configured is expected


def test_config_trims_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "  test-key  ")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "  eastasia  ")

    config = AzureSpeechConfig.from_env()

    assert config.key == "test-key"
    assert config.region == "eastasia"
    assert config.configured is True
