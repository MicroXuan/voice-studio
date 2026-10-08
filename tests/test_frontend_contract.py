import re

import pytest

from tests.conftest import ApiHarness


@pytest.mark.asyncio
async def test_root_serves_chinese_html_and_local_assets(
    api_harness: ApiHarness,
) -> None:
    response = await api_harness.client.get("/")

    assert response.status_code == 200
    assert 'lang="zh-CN"' in response.text
    assert 'href="/static/styles.css"' in response.text
    assert "fonts.googleapis.com" not in response.text

    stylesheet = await api_harness.client.get("/static/styles.css")
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")


@pytest.mark.asyncio
async def test_textarea_and_controls_have_explicit_labels(
    api_harness: ApiHarness,
) -> None:
    html = (await api_harness.client.get("/")).text

    for control_id in ["text-input", "rate", "pitch", "volume"]:
        assert re.search(rf'<label[^>]+for="{control_id}"', html)
    assert '<fieldset id="voice-list"' in html
    assert "<legend>选择声音</legend>" in html


@pytest.mark.asyncio
async def test_status_region_is_live_and_progress_has_accessible_values(
    api_harness: ApiHarness,
) -> None:
    html = (await api_harness.client.get("/")).text

    assert re.search(r'id="job-status"[^>]+aria-live="polite"', html)
    assert re.search(
        r'id="progress-bar"[^>]+role="progressbar"[^>]+'
        r'aria-valuemin="0"[^>]+aria-valuemax="100"[^>]+'
        r'aria-valuenow="0"',
        html,
    )
    assert 'id="progress-percent"' in html


@pytest.mark.asyncio
async def test_audio_result_has_stable_hidden_container(
    api_harness: ApiHarness,
) -> None:
    html = (await api_harness.client.get("/")).text

    assert re.search(r'<section[^>]+id="audio-result"[^>]+hidden', html)
    assert '<audio id="audio-player"' in html
    assert 'id="download-link"' in html


@pytest.mark.asyncio
async def test_css_contains_approved_tokens_and_44px_targets(
    api_harness: ApiHarness,
) -> None:
    css = (await api_harness.client.get("/static/styles.css")).text.upper()

    for color in ["#F4F7F9", "#10233C", "#1F6FEB", "#FF6B4A", "#DCE6EF"]:
        assert color in css
    assert "MIN-HEIGHT: 44PX" in css
    assert "FONT-SIZE: 16PX" in css


@pytest.mark.asyncio
async def test_css_has_375_768_1024_breakpoints_and_reduced_motion_rule(
    api_harness: ApiHarness,
) -> None:
    css = (await api_harness.client.get("/static/styles.css")).text

    assert "min-width: 375px" in css
    assert "min-width: 768px" in css
    assert "min-width: 1024px" in css
    assert "prefers-reduced-motion: reduce" in css


@pytest.mark.asyncio
async def test_html_has_no_emoji_icons_or_placeholder_only_inputs(
    api_harness: ApiHarness,
) -> None:
    html = (await api_harness.client.get("/")).text

    assert not re.search(r"[\U0001F300-\U0001FAFF]", html)
    assert " placeholder=" not in html
    assert "<svg" in html
