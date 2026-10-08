# Azure Yunze Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Azure Speech-backed `zh-CN-YunzeNeural` to the existing local Voice Studio while preserving all current Edge TTS voices and keeping Azure credentials server-side.

**Architecture:** Load Azure credentials into a focused configuration object, derive voice availability at application startup, and route synthesis by each voice's provider. A small asynchronous Azure REST client produces MP3 through the same job and file lifecycle already used by Edge TTS; the frontend consumes availability metadata and disables Yunze when Azure is not configured.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, aiohttp, python-dotenv, edge-tts, vanilla JavaScript/CSS, pytest, pytest-asyncio, httpx

**Spec:** `docs/superpowers/specs/2026-10-08-azure-yunze-design.md`

## Global Constraints

- Keep the existing 20,000-character request limit and one-active-job behavior.
- `zh-CN-YunzeNeural` is Azure-only; all five existing voices stay on Edge TTS.
- Use Azure Speech REST through the existing `aiohttp` dependency path; do not add the Azure Speech SDK.
- Read only `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`; the current region value is `eastasia`.
- Never return, log, embed in JavaScript, document, or commit the real Azure key.
- Write audio to `.mp3.part`, atomically replace the final MP3 only after a non-empty response, and remove partial files after failure or cancellation.
- When Azure is unconfigured, keep Yunze visible but disabled and leave every Edge voice usable.
- Preserve the existing job polling, playback, and download APIs.

## Review Focus

- Only one of Key or Region is set: Yunze must remain unavailable, with no attempt to guess or partially use credentials; Task 1 pins this behavior.
- Text contains `&`, `<`, `>`, quotes, or Chinese punctuation: generated SSML must remain valid and preserve the spoken text; Task 2 pins this behavior.
- Azure returns 401 or 403 with a detailed response body: the job must show only the stable configuration error and never expose the upstream body; Tasks 2 and 3 pin this behavior.
- Azure returns 429: the job must explain that free quota or request frequency may be the cause and must release the active-job slot; Tasks 2 and 3 pin this behavior.
- A disabled Yunze radio passes through busy/unbusy transitions: it must stay disabled and another available voice must remain selected; Task 4 pins this behavior.

---

## File Structure

- Create `app/config.py`: load and validate local Azure Speech environment settings.
- Create `app/azure_tts_service.py`: build SSML, call Azure REST, map Azure failures, and safely persist MP3.
- Create `app/tts_router.py`: expose one synthesizer interface and route each voice to Edge or Azure.
- Modify `app/models.py`: add provider and runtime availability fields to voice responses.
- Modify `app/voices.py`: define Yunze and produce a runtime catalog based on Azure configuration.
- Modify `app/tts_service.py`: formalize the shared synthesizer/progress interface and retain Edge implementation.
- Modify `app/main.py`: construct configuration/services/catalog, reject unavailable voices, and map provider errors to public messages.
- Modify `static/app.js` and `static/styles.css`: render Azure metadata and preserve disabled state.
- Modify `requirements.txt`, `.gitignore`, `.env.example`, and `README.md`: support safe local configuration and document usage.
- Modify focused files under `tests/`: pin every backend, frontend, and repository contract above without real Azure calls.

### Task 1: Azure Configuration and Runtime Voice Catalog

**Files:**
- Create: `app/config.py`
- Modify: `app/models.py`
- Modify: `app/voices.py`
- Modify: `requirements.txt`
- Test: `tests/test_models.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `AzureSpeechConfig(key: str | None, region: str | None)` with `AzureSpeechConfig.from_env() -> AzureSpeechConfig` and `configured: bool`.
- Produces: `VoiceOption.provider: Literal["edge", "azure"]`, `available: bool`, and `unavailable_reason: str | None`.
- Produces: `build_voice_catalog(azure_configured: bool) -> tuple[VoiceOption, ...]` and `get_voice(voice_id: str, catalog: tuple[VoiceOption, ...]) -> VoiceOption | None`.
- Consumes: no interfaces from later tasks.

- [ ] **Step 1: Write failing configuration and catalog tests**

Add tests named `test_config_requires_both_key_and_region`, `test_config_trims_environment_values`, and `test_voice_catalog_includes_azure_yunze_with_runtime_availability`. Assert that empty or one-sided credentials yield `configured is False`; both nonblank values yield `True`; Yunze has provider `azure`; existing voices have provider `edge`; Yunze is disabled with reason `需配置 Azure Speech` only when configuration is incomplete.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest tests/test_config.py tests/test_models.py -v`

Expected: FAIL because `AzureSpeechConfig`, the new voice fields, and Yunze catalog entry do not exist.

- [ ] **Step 3: Implement the configuration and catalog interfaces**

Add `python-dotenv>=1,<2` to `requirements.txt`. `AzureSpeechConfig.from_env()` calls `load_dotenv()` and reads only the two specified variables. Add the voice fields with safe defaults for existing callers, add Yunze, and make `build_voice_catalog()` create immutable runtime models rather than mutate module globals.

- [ ] **Step 4: Run focused tests and the existing model suite**

Run: `python -m pytest tests/test_config.py tests/test_models.py -v`

Expected: PASS, including uniqueness of all six voice IDs and both partial-credential cases.

- [ ] **Step 5: Commit the configuration and catalog**

```bash
git add app/config.py app/models.py app/voices.py requirements.txt tests/test_config.py tests/test_models.py
git commit -m "feat: add Azure-aware voice catalog"
```

### Task 2: Azure Speech REST Client

**Files:**
- Create: `app/azure_tts_service.py`
- Modify: `app/tts_service.py`
- Create: `tests/test_azure_tts_service.py`
- Modify: `tests/test_tts_service.py`

**Interfaces:**
- Consumes: `AzureSpeechConfig` from Task 1.
- Produces: `ProgressCallback = Callable[[int, str], Awaitable[None]]` and `SpeechSynthesizer` protocol with the existing synthesis arguments.
- Produces: `AzureTTSService(config: AzureSpeechConfig, session_factory: Callable[..., Any] = aiohttp.ClientSession)` implementing `synthesize(...) -> None`.
- Produces: `TTSAuthenticationError`, `TTSQuotaError`, `TTSServiceError`, while retaining `TTSUnavailableError`, `EmptyAudioError`, and `AudioWriteError`.

- [ ] **Step 1: Update shared interface tests and write Azure success tests**

Add fake async session/response objects and tests named `test_azure_posts_escaped_ssml_to_regional_endpoint`, `test_azure_writes_nonempty_mp3_atomically`, and `test_azure_reports_stage_progress`. Assert endpoint `https://eastasia.tts.speech.microsoft.com/cognitiveservices/v1`, voice `zh-CN-YunzeNeural`, output format `audio-24khz-48kbitrate-mono-mp3`, escaped special text, signed percentage controls, final MP3 bytes, no remaining `.part`, and the exact stages `(10, "正在连接 Azure")`, `(70, "正在合成语音")`, and `(90, "正在保存音频")`.

Update Edge tests and their callback helpers to accept `(progress: int, message: str)`, retaining all existing Edge assertions.

- [ ] **Step 2: Run focused service tests and verify they fail**

Run: `python -m pytest tests/test_azure_tts_service.py tests/test_tts_service.py -v`

Expected: FAIL because the Azure service, shared callback shape, and Azure errors do not exist.

- [ ] **Step 3: Implement the minimal Azure REST client and shared interface**

Build SSML with `xml.etree.ElementTree` so text and attributes are escaped by construction. Send the key only through `Ocp-Apim-Subscription-Key`; set `Content-Type`, `X-Microsoft-OutputFormat`, and a stable `User-Agent`. Stream or read response bytes into `.part`, require a non-empty file, then replace the final path.

- [ ] **Step 4: Add failing failure-path tests**

Add parameterized tests for 401/403 → `TTSAuthenticationError`, 429 → `TTSQuotaError`, other 4xx/5xx → `TTSServiceError`, connection/timeout → `TTSUnavailableError`, empty 200 → `EmptyAudioError`, write denial → `AudioWriteError`, and cancellation. Assert exception strings do not contain fake upstream response bodies or the fake key, and every case removes `.part`.

- [ ] **Step 5: Implement status/error mapping and cleanup, then rerun tests**

Run: `python -m pytest tests/test_azure_tts_service.py tests/test_tts_service.py -v`

Expected: PASS for success, XML special characters, all status classes, network failure, empty audio, write failure, and cancellation.

- [ ] **Step 6: Commit the Azure client**

```bash
git add app/azure_tts_service.py app/tts_service.py tests/test_azure_tts_service.py tests/test_tts_service.py
git commit -m "feat: add Azure Speech REST client"
```

### Task 3: Provider Router and Job API Integration

**Files:**
- Create: `app/tts_router.py`
- Modify: `app/main.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_tts_router.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: runtime voice catalog from Task 1 and `SpeechSynthesizer` implementations/errors from Task 2.
- Produces: `TTSRouter(catalog, edge_service, azure_service)` implementing `synthesize(...)` and selecting by `VoiceOption.provider`.
- Produces: `create_app(store=None, tts_service=None, azure_config=None, catalog=None) -> FastAPI`, where `tts_service` remains a full-router test override and production construction creates Edge/Azure services from configuration.

- [ ] **Step 1: Write failing router tests**

Add `test_router_sends_edge_voice_only_to_edge`, `test_router_sends_yunze_only_to_azure`, and `test_router_rejects_unavailable_or_unknown_voice`. Use recording synthesizers and assert each request reaches exactly one provider with unchanged text, controls, output path, and callback.

- [ ] **Step 2: Run router tests and verify they fail**

Run: `python -m pytest tests/test_tts_router.py -v`

Expected: FAIL because `TTSRouter` does not exist.

- [ ] **Step 3: Implement `TTSRouter`**

Resolve the voice from its injected catalog, reject unknown/unavailable voices without calling either provider, and delegate the original voice ID and synthesis arguments to the selected service.

- [ ] **Step 4: Write failing API availability and public-error tests**

Extend the API harness so tests can inject a catalog/router. Add tests asserting `/api/voices` returns Yunze with `available` and no credential fields; unavailable Yunze receives HTTP 422 before job creation; configured Yunze can create a job; progress messages supplied by the provider reach job polling; authentication, quota, service, network, empty-audio, and write errors each become the exact stable Chinese messages from the spec; a failed job releases the slot so the next job can start.

- [ ] **Step 5: Run API tests and verify they fail for the new contract**

Run: `python -m pytest tests/test_api.py -v`

Expected: FAIL on runtime catalog construction, Yunze availability, stage messages, and Azure error mapping.

- [ ] **Step 6: Integrate configuration, router, catalog, and public errors in `app/main.py`**

Production startup builds one config, catalog, Edge service, optional Azure service, and router. `_run_job()` accepts `ProgressCallback` messages and catches specific errors before generic ones. No exception detail or config object is serialized to clients.

- [ ] **Step 7: Run backend integration tests**

Run: `python -m pytest tests/test_tts_router.py tests/test_api.py tests/test_job_store.py -v`

Expected: PASS; existing Edge jobs still complete and each failed Azure class releases the one-job lock.

- [ ] **Step 8: Commit router and API integration**

```bash
git add app/tts_router.py app/main.py tests/conftest.py tests/test_tts_router.py tests/test_api.py
git commit -m "feat: route Yunze jobs through Azure"
```

### Task 4: Disabled Yunze Frontend State

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: `/api/voices` fields `provider`, `available`, and `unavailable_reason` from Tasks 1 and 3.
- Produces: accessible voice cards that mark Azure, disable unavailable voices, select the first available voice, preserve provider-disabled state across `setBusy(true/false)`, and show pitch in `%` for Azure or `Hz` for Edge.

- [ ] **Step 1: Write failing frontend contract tests**

Add tests that require `renderVoiceChoices()` to set `radio.disabled = !voice.available`, store persistent availability and provider metadata on each radio, check only the first available voice, render `voice.unavailable_reason`, and render an Azure label without using emoji. Require `setBusy()` to disable a radio when either the form is busy or its stored availability is false, and require pitch labels to use `%` for Azure or `Hz` for Edge.

- [ ] **Step 2: Run the frontend contract tests and verify they fail**

Run: `python -m pytest tests/test_frontend_contract.py -v`

Expected: FAIL because the current renderer assumes every voice is available and re-enables every radio after a job.

- [ ] **Step 3: Implement accessible available/disabled card behavior**

Use text labels and CSS classes for the Azure badge and unavailable reason. Keep unavailable inputs in the DOM for discoverability, but disabled for mouse and keyboard. If no voice is available, leave all unchecked and keep the generate button disabled. Recompute the pitch unit when voice selection changes and after voices load so the UI matches each provider's SSML control.

- [ ] **Step 4: Add and style disabled/Azure states**

Give disabled cards sufficient contrast, a non-interactive cursor, and no hover/checked affordance. Preserve the existing touch target, focus visibility, breakpoints, and reduced-motion rules.

- [ ] **Step 5: Run frontend and API contract tests**

Run: `python -m pytest tests/test_frontend_contract.py tests/test_api.py -v`

Expected: PASS, including the busy/unbusy disabled-state regression and first-available selection.

- [ ] **Step 6: Commit the frontend integration**

```bash
git add static/app.js static/styles.css tests/test_frontend_contract.py
git commit -m "feat: show Azure Yunze availability"
```

### Task 5: Safe Local Setup, Documentation, and End-to-End Verification

**Files:**
- Create: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`
- Create: `tests/test_configuration_contract.py`

**Interfaces:**
- Consumes: the environment names and startup behavior from Tasks 1–4.
- Produces: a copyable secret-free configuration template and verified local setup instructions.

- [ ] **Step 1: Write failing repository-safety tests**

Add tests asserting `.gitignore` contains an exact `.env` rule, `.env.example` contains the two variable names with an empty key and `AZURE_SPEECH_REGION=eastasia`, the example contains no key-like value, and `README.md` documents Yunze, F0 awareness, restart-after-config, and the instruction never to commit or share the key.

- [ ] **Step 2: Run the contract test and verify it fails**

Run: `python -m pytest tests/test_configuration_contract.py -v`

Expected: FAIL because `.env.example` and the Azure setup documentation do not exist.

- [ ] **Step 3: Add safe configuration files and update documentation**

Document copying `.env.example` to `.env`, locally filling Key and `eastasia`, restarting Uvicorn, recognizing disabled Yunze when configuration is absent, and rotating a key if it is exposed. Replace the obsolete README explanation that Yunze is unavailable with the new provider split.

- [ ] **Step 4: Run the complete automated verification**

Run: `python -m pytest -v`

Expected: all tests PASS with no real Azure variables required.

Run: `python -m compileall -q app`

Expected: exit code 0 and no output.

- [ ] **Step 5: Check the repository for accidental credentials**

Run: `git diff --check && git status --short && rg -n "AZURE_SPEECH_KEY\s*=.+" --glob '!*.md' --glob '!.env' .`

Expected: no whitespace errors; only intended files are modified; no committed file contains a non-empty Azure key assignment.

- [ ] **Step 6: Commit configuration and documentation**

```bash
git add .env.example .gitignore README.md tests/test_configuration_contract.py
git commit -m "docs: add safe Azure Speech setup"
```

- [ ] **Step 7: Configure the real key without echoing it**

In the local worktree, create `.env` from `.env.example`, then enter `AZURE_SPEECH_KEY` through a silent terminal prompt or a local editor. Confirm `.env` is ignored with `git check-ignore -v .env`. Do not print, paste into chat, or add `.env` to Git.

- [ ] **Step 8: Restart and perform a real Yunze smoke test**

Restart Uvicorn, request `/api/voices` and confirm Yunze is available without inspecting the secret, then generate a short sentence with Yunze in the browser. Verify the job reaches 100%, the audio plays, the MP3 download is non-empty, the five Edge voices remain selectable, and no secret appears in browser developer tools or server logs.

- [ ] **Step 9: Record final verification state**

Run: `git status --short && git log -5 --oneline`

Expected: clean worktree, five focused implementation/documentation commits after the approved design and plan commits.
