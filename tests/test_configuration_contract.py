import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_env_example_is_secret_free_and_uses_eastasia() -> None:
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assignments = dict(
        line.split("=", 1)
        for line in example.splitlines()
        if line and not line.startswith("#")
    )

    assert assignments == {
        "AZURE_SPEECH_KEY": "",
        "AZURE_SPEECH_REGION": "eastasia",
    }


def test_local_env_is_ignored_by_git() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=PROJECT_ROOT,
        check=False,
    )

    assert result.returncode == 0
