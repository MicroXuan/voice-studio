import re

import pytest

from tests.conftest import ApiHarness


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first, second = luminance(foreground), luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


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


@pytest.mark.asyncio
async def test_script_is_deferred_and_uses_required_api_routes(
    api_harness: ApiHarness,
) -> None:
    html = (await api_harness.client.get("/")).text
    assert '<script src="/static/app.js" defer></script>' in html

    script_response = await api_harness.client.get("/static/app.js")
    assert script_response.status_code == 200
    script = script_response.text
    assert 'fetch("/api/voices")' in script
    assert 'fetch("/api/jobs"' in script
    assert "fetch(`/api/jobs/${jobId}`)" in script


@pytest.mark.asyncio
async def test_ui_prevents_empty_submission_and_preserves_text_on_error(
    api_harness: ApiHarness,
) -> None:
    script = (await api_harness.client.get("/static/app.js")).text

    assert "function serializeRequest()" in script
    assert "elements.text.value.trim()" in script
    assert "if (!payload.text)" in script
    error_function = script.split("function renderError", 1)[1].split(
        "function ", 1
    )[0]
    assert "elements.text.value =" not in error_function


@pytest.mark.asyncio
async def test_polling_has_retry_path_for_transient_fetch_failure(
    api_harness: ApiHarness,
) -> None:
    script = (await api_harness.client.get("/static/app.js")).text

    assert "const POLL_INTERVAL = 800" in script
    assert "继续查询" in script
    assert "pollJob(activeJobId)" in script


@pytest.mark.asyncio
async def test_completed_state_sets_player_and_download_urls(
    api_harness: ApiHarness,
) -> None:
    script = (await api_harness.client.get("/static/app.js")).text

    assert "elements.audioPlayer.src = job.audio_url" in script
    assert "elements.downloadLink.href = `${job.audio_url}?download=true`" in script
    assert "elements.audioResult.hidden = false" in script


@pytest.mark.asyncio
async def test_waveform_is_not_the_only_progress_signal(
    api_harness: ApiHarness,
) -> None:
    script = (await api_harness.client.get("/static/app.js")).text

    assert 'elements.progressBar.setAttribute("aria-valuenow", String(progress))' in script
    assert "elements.progressPercent.textContent = `${progress}%`" in script
    assert 'style.setProperty("--progress", `${progress}%`)' in script


@pytest.mark.asyncio
async def test_accessibility_audit_has_skip_link_touch_optimization_and_contrast(
    api_harness: ApiHarness,
) -> None:
    html = (await api_harness.client.get("/")).text
    css = (await api_harness.client.get("/static/styles.css")).text

    assert 'class="skip-link" href="#main-content"' in html
    assert '<main class="page-shell" id="main-content"' in html
    assert "touch-action: manipulation" in css
    assert "button:active" in css

    paper = re.search(r"--paper:\s*(#[0-9A-Fa-f]{6})", css).group(1)
    muted = re.search(r"--muted:\s*(#[0-9A-Fa-f]{6})", css).group(1)
    assert contrast_ratio(muted, paper) >= 4.5


@pytest.mark.asyncio
async def test_mobile_text_action_prevents_label_wrap(
    api_harness: ApiHarness,
) -> None:
    css = (await api_harness.client.get("/static/styles.css")).text
    text_action_rule = re.search(r"\.text-action\s*\{([^}]+)\}", css).group(1)

    assert "white-space: nowrap" in text_action_rule
    assert "flex-shrink: 0" in text_action_rule
