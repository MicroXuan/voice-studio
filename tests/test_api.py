import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models import JobState
from tests.conftest import ApiHarness


async def wait_for_state(
    harness: ApiHarness, job_id: str, state: JobState, attempts: int = 40
) -> dict:
    for _ in range(attempts):
        response = await harness.client.get(f"/api/jobs/{job_id}")
        if response.status_code == 200 and response.json()["state"] == state.value:
            return response.json()
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {state.value}")


@pytest.mark.asyncio
async def test_get_voices_returns_curated_catalog(api_harness: ApiHarness) -> None:
    response = await api_harness.client.get("/api/voices")

    assert response.status_code == 200
    ids = {voice["id"] for voice in response.json()}
    assert {
        "zh-CN-YunxiNeural",
        "zh-CN-YunzeNeural",
        "zh-CN-XiaoxiaoNeural",
    } <= ids


@pytest.mark.asyncio
async def test_create_job_rejects_unknown_voice(api_harness: ApiHarness) -> None:
    response = await api_harness.client.post(
        "/api/jobs", json={"text": "测试", "voice": "unknown"}
    )

    assert response.status_code == 422
    assert "声音" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_job_returns_202_and_poll_url(api_harness: ApiHarness) -> None:
    response = await api_harness.client.post(
        "/api/jobs",
        json={"text": "测试", "voice": "zh-CN-YunxiNeural"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["state"] == "queued"
    assert response.headers["location"] == f"/api/jobs/{payload['id']}"


@pytest.mark.asyncio
async def test_second_active_job_returns_409(api_harness: ApiHarness) -> None:
    first = await api_harness.client.post(
        "/api/jobs",
        json={"text": "第一条", "voice": "zh-CN-YunxiNeural"},
    )
    await asyncio.wait_for(api_harness.synthesizer.started.wait(), timeout=1)

    second = await api_harness.client.post(
        "/api/jobs",
        json={"text": "第二条", "voice": "zh-CN-YunzeNeural"},
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert "正在生成" in second.json()["detail"]


@pytest.mark.asyncio
async def test_job_moves_to_completed_with_audio_url(api_harness: ApiHarness) -> None:
    api_harness.synthesizer.release.set()
    created = await api_harness.client.post(
        "/api/jobs",
        json={"text": "完成测试", "voice": "zh-CN-YunxiNeural"},
    )
    job_id = created.json()["id"]

    job = await wait_for_state(api_harness, job_id, JobState.COMPLETED)

    assert job["progress"] == 100
    assert job["audio_url"] == f"/api/jobs/{job_id}/audio"


@pytest.mark.asyncio
async def test_tts_failure_returns_public_chinese_error_without_exception_detail(
    api_harness: ApiHarness,
) -> None:
    api_harness.synthesizer.mode = "failure"
    api_harness.synthesizer.release.set()
    created = await api_harness.client.post(
        "/api/jobs",
        json={"text": "失败测试", "voice": "zh-CN-YunxiNeural"},
    )

    job = await wait_for_state(api_harness, created.json()["id"], JobState.FAILED)

    assert "检查网络" in job["error"]
    assert "private upstream detail" not in job["error"]


@pytest.mark.asyncio
async def test_unknown_job_and_expired_job_return_404(
    api_harness: ApiHarness,
) -> None:
    unknown = await api_harness.client.get(f"/api/jobs/{uuid4()}")
    assert unknown.status_code == 404

    api_harness.synthesizer.release.set()
    created = await api_harness.client.post(
        "/api/jobs",
        json={"text": "过期测试", "voice": "zh-CN-YunxiNeural"},
    )
    job_id = created.json()["id"]
    await wait_for_state(api_harness, job_id, JobState.COMPLETED)
    await api_harness.store.cleanup_expired(
        now=datetime.now(UTC) + timedelta(hours=2)
    )

    expired = await api_harness.client.get(f"/api/jobs/{job_id}")
    assert expired.status_code == 404


@pytest.mark.asyncio
async def test_running_or_failed_audio_returns_409(api_harness: ApiHarness) -> None:
    running = await api_harness.client.post(
        "/api/jobs",
        json={"text": "运行中", "voice": "zh-CN-YunxiNeural"},
    )
    await asyncio.wait_for(api_harness.synthesizer.started.wait(), timeout=1)
    running_audio = await api_harness.client.get(
        f"/api/jobs/{running.json()['id']}/audio"
    )
    assert running_audio.status_code == 409

    api_harness.synthesizer.mode = "failure"
    api_harness.synthesizer.release.set()
    await wait_for_state(api_harness, running.json()["id"], JobState.FAILED)
    failed_audio = await api_harness.client.get(
        f"/api/jobs/{running.json()['id']}/audio"
    )
    assert failed_audio.status_code == 409


@pytest.mark.asyncio
async def test_completed_audio_supports_inline_and_attachment(
    api_harness: ApiHarness,
) -> None:
    api_harness.synthesizer.release.set()
    created = await api_harness.client.post(
        "/api/jobs",
        json={"text": "音频响应", "voice": "zh-CN-YunxiNeural"},
    )
    job_id = created.json()["id"]
    await wait_for_state(api_harness, job_id, JobState.COMPLETED)

    inline = await api_harness.client.get(f"/api/jobs/{job_id}/audio")
    attachment = await api_harness.client.get(
        f"/api/jobs/{job_id}/audio?download=true"
    )

    assert inline.status_code == 200
    assert inline.content == b"test-mp3"
    assert inline.headers["content-type"] == "audio/mpeg"
    assert inline.headers["content-disposition"].startswith("inline;")
    assert attachment.headers["content-disposition"].startswith("attachment;")
    assert f"voice-studio-{job_id}.mp3" in attachment.headers["content-disposition"]


@pytest.mark.asyncio
async def test_empty_generated_file_is_not_downloadable(
    api_harness: ApiHarness,
) -> None:
    api_harness.synthesizer.mode = "empty"
    api_harness.synthesizer.release.set()
    created = await api_harness.client.post(
        "/api/jobs",
        json={"text": "空音频", "voice": "zh-CN-YunxiNeural"},
    )
    job_id = created.json()["id"]
    await wait_for_state(api_harness, job_id, JobState.FAILED)

    response = await api_harness.client.get(f"/api/jobs/{job_id}/audio")

    assert response.status_code == 409
