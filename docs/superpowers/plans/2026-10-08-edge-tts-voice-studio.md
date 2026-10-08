# 声屿 Voice Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个本地运行的中文文本转语音网站，可用精选 Edge TTS 声音将最多 20,000 字文本生成、试听并下载为 MP3。

**Architecture:** FastAPI 单体应用同时提供 JSON API 和无构建步骤的静态前端。后台任务流式调用 `edge-tts`，内存任务仓库维护状态，音频写入独立临时目录并按保留时间清理。

**Tech Stack:** Python 3.11+、FastAPI、Uvicorn、edge-tts、Pydantic、pytest、HTTPX、原生 HTML/CSS/JavaScript

**Spec:** `docs/superpowers/specs/2026-10-08-edge-tts-voice-studio-design.md`

## Global Constraints

- 第一版仅支持单个本地用户，同一时间最多一个运行中的合成任务。
- 文本去除首尾空白后必须非空，最大长度为 20,000 个 Unicode 字符。
- `rate`、`pitch`、`volume` 均使用整数 API 值，允许范围为 `-50` 到 `50`；传给 `edge-tts` 时分别格式化为带符号的 `%`、`Hz`、`%` 字符串。
- 任务状态固定为 `queued`、`running`、`completed`、`failed`，运行进度不得倒退，验证音频前不得达到 100%。
- 生成结果仅为 MP3；不实现账号、数据库、历史记录、SRT、声音克隆、云存储或高级 SSML。
- 前端不使用 Node.js 构建链，不使用 emoji 图标，不以占位符替代表单标签。
- 所有可点击控件最小尺寸为 44×44px；正文基础字号不小于 16px；支持键盘焦点与 `prefers-reduced-motion`。
- 页面必须在 375px、768px、1024px 和 1440px 宽度下无横向滚动。
- 用户可见错误使用稳定中文文案；堆栈、内部路径和底层异常详情仅写入服务端日志。

## Review Focus

- 只包含空格或换行的文本应作为空文本返回 422，而不是创建无声任务；由 Task 1 的模型测试固定。
- 两个请求几乎同时到达时只能有一个任务进入运行，其余请求得到 409；由 Task 2 和 Task 4 的并发测试固定。
- `edge-tts` 只产生边界事件却没有音频，或留下空文件时任务必须失败且不可下载；由 Task 3 和 Task 4 的测试固定。
- 未知、未完成、失败和过期任务的音频访问必须分别返回稳定的 404 或 409；由 Task 4 的接口测试固定。
- 浏览器刷新或轮询遇到瞬时网络错误时应保留输入和任务 ID，并允许继续重试；由 Task 6 的状态逻辑与人工验收固定。

---

## File Map

- `requirements.txt`：运行与测试依赖的兼容版本范围。
- `.gitignore`：忽略 Python 缓存、虚拟环境、测试缓存和本地生成物。
- `app/__init__.py`：应用包标记。
- `app/models.py`：声音、合成请求、任务状态和 API 响应模型。
- `app/voices.py`：唯一的精选中文声音清单与查询函数。
- `app/job_store.py`：并发安全的单任务内存仓库和过期文件清理。
- `app/tts_service.py`：`edge-tts` 流式合成、进度估算和原子文件写入。
- `app/main.py`：应用工厂、后台任务编排、API 路由和静态文件托管。
- `static/index.html`：语义化工作台页面。
- `static/styles.css`：设计令牌、响应式布局、状态与动画。
- `static/app.js`：表单状态、任务创建与轮询、波形、播放和下载。
- `tests/conftest.py`：临时目录、测试应用与可控合成器夹具。
- `tests/test_models.py`：输入规范与声音清单测试。
- `tests/test_job_store.py`：任务生命周期、并发与清理测试。
- `tests/test_tts_service.py`：流处理、进度、文件与异常测试。
- `tests/test_api.py`：端到端 API 状态与音频响应测试。
- `tests/test_frontend_contract.py`：HTML/CSS/JS 的关键无障碍和交互契约检查。
- `README.md`：安装、启动、使用、限制和故障排查。

### Task 1: 项目基础、声音清单与请求模型

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/models.py`
- Create: `app/voices.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: 无。
- Produces: `VoiceOption`、`SynthesisRequest`、`JobState`、`JobResponse`、`VOICES: tuple[VoiceOption, ...]`、`get_voice(voice_id: str) -> VoiceOption | None`。

- [ ] **Step 1: Write failing model and voice tests**

在 `tests/test_models.py` 添加：`test_whitespace_text_is_rejected`、`test_text_over_20000_characters_is_rejected`、`test_controls_accept_minus_50_and_50`、`test_controls_reject_out_of_range_values`、`test_voice_catalog_contains_yunxi_yunze_and_female_voice`。断言空白文本与 20,001 字失败，边界值通过，清单包含 `zh-CN-YunxiNeural`、`zh-CN-YunzeNeural`、`zh-CN-XiaoxiaoNeural` 且 voice ID 唯一。

- [ ] **Step 2: Run tests and verify collection/import failure**

Run: `python -m pytest tests/test_models.py -v`

Expected: FAIL because `app.models` and `app.voices` do not exist.

- [ ] **Step 3: Add dependencies and implement the exact models**

在 `requirements.txt` 声明 `fastapi>=0.115,<1`、`uvicorn[standard]>=0.34,<1`、`edge-tts>=7.2,<8`、`pytest>=8,<9`、`pytest-asyncio>=0.25,<2`、`httpx>=0.28,<1`。在 `app/models.py` 实现：

- `VoiceOption(id: str, name: str, gender: Literal["男声", "女声"], description: str)`
- `SynthesisRequest(text: str, voice: str, rate: int = 0, pitch: int = 0, volume: int = 0)`，文本 strip 后校验 1–20,000 字，三个整数均限制到 `-50..50`
- `JobState(str, Enum)` 四个固定状态
- `JobResponse(id: UUID, state: JobState, progress: int, message: str, error: str | None = None, audio_url: str | None = None)`

在 `app/voices.py` 提供不可变清单，至少包含云希、云泽、晓晓，并实现 `get_voice`。

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_models.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the foundation**

```bash
git add requirements.txt .gitignore app tests/test_models.py
git commit -m "feat: define voice studio input models"
```

### Task 2: 单任务内存仓库与临时文件生命周期

**Files:**
- Create: `app/job_store.py`
- Create: `tests/test_job_store.py`

**Interfaces:**
- Consumes: `JobState` from Task 1.
- Produces: `JobRecord` dataclass；`JobStore(output_dir: Path, retention_seconds: int = 3600)`；异步方法 `create() -> JobRecord`、`get(job_id: UUID) -> JobRecord | None`、`start(job_id: UUID) -> None`、`update_progress(job_id: UUID, progress: int, message: str) -> None`、`complete(job_id: UUID, output_path: Path) -> None`、`fail(job_id: UUID, public_error: str) -> None`、`cleanup_expired(now: datetime | None = None) -> int`；异常 `ActiveJobError`。

- [ ] **Step 1: Write failing lifecycle, monotonic-progress, concurrency, and cleanup tests**

在 `tests/test_job_store.py` 添加：

- `test_job_moves_queued_running_completed`
- `test_progress_never_moves_backwards_or_above_95_while_running`
- `test_only_one_active_job_can_be_created`
- `test_concurrent_create_allows_exactly_one_job`
- `test_failed_job_releases_active_slot`
- `test_cleanup_removes_expired_record_and_owned_audio`
- `test_cleanup_does_not_delete_file_outside_output_dir`

并发测试使用 `asyncio.gather` 同时调用两次 `create`，断言一条成功、一条 `ActiveJobError`。

- [ ] **Step 2: Run tests and verify import failure**

Run: `python -m pytest tests/test_job_store.py -v`

Expected: FAIL because `app.job_store` does not exist.

- [ ] **Step 3: Implement the locked store and safe cleanup**

所有读写通过同一个 `asyncio.Lock`。`complete` 只有在输出文件存在且非空时设置 100；`fail` 和 `complete` 必须释放活动任务槽。清理只允许删除 `output_dir.resolve()` 内由任务记录引用的文件，不跟随任意外部路径。

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_job_store.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the store**

```bash
git add app/job_store.py tests/test_job_store.py
git commit -m "feat: add in-memory synthesis job store"
```

### Task 3: Edge TTS 流式合成服务

**Files:**
- Create: `app/tts_service.py`
- Create: `tests/test_tts_service.py`

**Interfaces:**
- Consumes: numeric control values from `SynthesisRequest`.
- Produces: `EdgeTTSService(communicate_factory=edge_tts.Communicate)`；`async synthesize(text: str, voice: str, rate: int, pitch: int, volume: int, output_path: Path, on_progress: Callable[[int], Awaitable[None]]) -> None`；`TTSUnavailableError`、`EmptyAudioError`、`AudioWriteError`。

- [ ] **Step 1: Write failing stream tests with a fake communicator**

在 `tests/test_tts_service.py` 添加：

- `test_formats_controls_with_explicit_sign`
- `test_writes_audio_chunks_to_final_mp3`
- `test_boundary_progress_is_monotonic_and_capped_at_95`
- `test_no_audio_raises_empty_audio_and_removes_partial_file`
- `test_network_exception_becomes_tts_unavailable`
- `test_write_exception_becomes_audio_write_error`

假流依次产生 `audio` 与 `WordBoundary` 字典；断言先写入同目录的 `.part` 文件，成功后原子替换目标，任何失败均不遗留 `.part` 或空 MP3。

- [ ] **Step 2: Run tests and verify import failure**

Run: `python -m pytest tests/test_tts_service.py -v`

Expected: FAIL because `app.tts_service` does not exist.

- [ ] **Step 3: Implement synthesis and exception translation**

`synthesize` 构造 `+0%`、`+0Hz`、`+0%` 形式的控制值；累计 WordBoundary 的 `text` 长度，以 `min(95, int(spoken_chars / len(text) * 95))` 估算并只上报更大的进度。底层连接类异常映射为 `TTSUnavailableError`，文件系统异常映射为 `AudioWriteError`，无音频数据映射为 `EmptyAudioError`。

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_tts_service.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the synthesizer**

```bash
git add app/tts_service.py tests/test_tts_service.py
git commit -m "feat: stream Edge TTS audio with progress"
```

### Task 4: FastAPI 编排、任务 API 与音频响应

**Files:**
- Create: `app/main.py`
- Create: `tests/conftest.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1 models/voices、Task 2 `JobStore`、Task 3 `EdgeTTSService.synthesize`。
- Produces: `create_app(store: JobStore | None = None, tts_service: EdgeTTSService | None = None) -> FastAPI`、模块级 `app`，以及规范中的四个 API。

- [ ] **Step 1: Write failing API contract tests**

在 `tests/test_api.py` 添加：

- `test_get_voices_returns_curated_catalog`
- `test_create_job_rejects_unknown_voice`
- `test_create_job_returns_202_and_poll_url`
- `test_second_active_job_returns_409`
- `test_job_moves_to_completed_with_audio_url`
- `test_tts_failure_returns_public_chinese_error_without_exception_detail`
- `test_unknown_job_and_expired_job_return_404`
- `test_running_or_failed_audio_returns_409`
- `test_completed_audio_supports_inline_and_attachment`
- `test_empty_generated_file_is_not_downloadable`

通过依赖注入的可控合成器确定何时成功或失败；API 测试不得访问真实微软服务。

- [ ] **Step 2: Run tests and verify import failure**

Run: `python -m pytest tests/test_api.py -v`

Expected: FAIL because `app.main` does not exist.

- [ ] **Step 3: Implement the app factory and background runner**

实现：

- `GET /api/voices` 返回清单
- `POST /api/jobs` 校验声音、创建任务、使用 `asyncio.create_task` 启动私有 `_run_job(...)`，返回 202
- `GET /api/jobs/{job_id}` 将内部记录转换为 `JobResponse`
- `GET /api/jobs/{job_id}/audio?download=false` 使用 `FileResponse`，固定安全文件名 `voice-studio-{job_id}.mp3`

将任务引用保存在 `app.state.background_tasks`；关闭应用时取消并 `gather` 未完成任务。启动时调用一次 `cleanup_expired`，创建、查询任务或请求音频前也调用清理，使超过保留时间的记录无需重启即可过期。错误映射固定为可操作中文文案，详细异常使用 `logger.exception`。

- [ ] **Step 4: Run API and full backend tests**

Run: `python -m pytest tests/test_models.py tests/test_job_store.py tests/test_tts_service.py tests/test_api.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the API**

```bash
git add app/main.py tests/conftest.py tests/test_api.py
git commit -m "feat: expose asynchronous TTS job API"
```

### Task 5: 语义化工作台与响应式视觉系统

**Files:**
- Create: `static/index.html`
- Create: `static/styles.css`
- Create: `tests/test_frontend_contract.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `/api/voices` and the approved visual design.
- Produces: stable DOM IDs `text-input`、`character-count`、`voice-list`、`rate`、`pitch`、`volume`、`reset-controls`、`generate-button`、`job-status`、`progress-bar`、`waveform`、`audio-result`、`audio-player`、`download-link`。

- [ ] **Step 1: Write failing static contract tests**

在 `tests/test_frontend_contract.py` 添加：

- `test_root_serves_chinese_html_and_local_assets`
- `test_textarea_and_controls_have_explicit_labels`
- `test_status_region_is_live_and_progress_has_accessible_values`
- `test_audio_result_has_stable_hidden_container`
- `test_css_contains_approved_tokens_and_44px_targets`
- `test_css_has_375_768_1024_breakpoints_and_reduced_motion_rule`
- `test_html_has_no_emoji_icons_or_placeholder_only_inputs`

- [ ] **Step 2: Run tests and verify root/static failure**

Run: `python -m pytest tests/test_frontend_contract.py -v`

Expected: FAIL because static assets and root route do not exist.

- [ ] **Step 3: Build the semantic HTML and CSS from the approved system**

实现冷白 `#F4F7F9`、墨蓝 `#10233C`、电波蓝 `#1F6FEB`、信号橙 `#FF6B4A`、白色表面和 `#DCE6EF` 边框令牌。桌面为 2:1 工作台，移动端为任务顺序单列；结果区预留稳定空间。声音指纹用语义无关的 SVG/CSS 柱组成，并配套可见文字状态。所有图标均为内联 SVG，装饰图形使用 `aria-hidden="true"`。

- [ ] **Step 4: Mount assets and run static contract tests**

在 `app/main.py` 挂载 `/static` 并让 `/` 返回 `static/index.html`。

Run: `python -m pytest tests/test_frontend_contract.py tests/test_api.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the visual shell**

```bash
git add static/index.html static/styles.css app/main.py tests/test_frontend_contract.py
git commit -m "feat: build responsive voice studio interface"
```

### Task 6: 浏览器状态、任务轮询与音频操作

**Files:**
- Create: `static/app.js`
- Modify: `static/index.html`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: Task 4 API and Task 5 DOM IDs.
- Produces: browser functions `loadVoices()`、`serializeRequest()`、`createJob()`、`pollJob(jobId)`、`renderJob(job)`、`renderError(message, retryAction)`、`resetControls()`、`updateWaveform(progress)`。

- [ ] **Step 1: Extend failing frontend contract tests**

添加：

- `test_script_is_deferred_and_uses_required_api_routes`
- `test_ui_prevents_empty_submission_and_preserves_text_on_error`
- `test_polling_has_retry_path_for_transient_fetch_failure`
- `test_completed_state_sets_player_and_download_urls`
- `test_waveform_is_not_the_only_progress_signal`

契约测试检查所需函数、路由、`aria-valuenow` 更新、错误重试入口和音频 URL 赋值；浏览器行为仍需 Task 7 人工验证。

- [ ] **Step 2: Run the tests and verify missing-script failure**

Run: `python -m pytest tests/test_frontend_contract.py -v`

Expected: FAIL because `static/app.js` does not exist or lacks the contracts.

- [ ] **Step 3: Implement form and job state behavior**

页面加载时获取声音；输入时更新字符数与按钮可用状态；提交时锁定关键控件并保存任务 ID；每 800ms 轮询。瞬时 fetch 失败不清除输入或任务 ID，显示“继续查询”按钮；服务端 failed 状态显示原文和参数不变的“重新生成”按钮。completed 状态设置 `<audio src>` 与下载链接，停止轮询并解锁表单。

- [ ] **Step 4: Implement waveform and reduced-motion-safe state transitions**

波形只使用 `transform`、`opacity` 和 CSS 变量更新；进度同步写入百分比文字、原生进度条或 ARIA 值。检测减少动画设置时关闭循环位移，不影响状态更新。

- [ ] **Step 5: Run frontend and full automated tests**

Run: `python -m pytest -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit browser behavior**

```bash
git add static/app.js static/index.html static/styles.css tests/test_frontend_contract.py
git commit -m "feat: connect voice studio UI to job API"
```

### Task 7: 本地运行说明与端到端验收

**Files:**
- Create: `README.md`
- Modify: `.gitignore`
- Modify: any file with a defect found by verification

**Interfaces:**
- Consumes: complete application from Tasks 1–6.
- Produces: documented local workflow and verified release candidate.

- [ ] **Step 1: Write README as an executable local workflow**

记录 Python 3.11+ 虚拟环境、`pip install -r requirements.txt`、`uvicorn app.main:app --reload`、访问 `http://127.0.0.1:8000`、运行 `python -m pytest -v`、Edge 在线服务限制、临时文件行为和常见网络错误处理。明确 `edge-tts` 是非官方客户端且需要联网。

- [ ] **Step 2: Run automated quality checks**

Run: `python -m pytest -v`

Expected: all tests PASS.

Run: `python -m compileall -q app`

Expected: exit code 0 with no output.

- [ ] **Step 3: Start the server and verify health in a separate shell**

Run: `uvicorn app.main:app --host 127.0.0.1 --port 8000`

Run separately: `curl -fsS http://127.0.0.1:8000/api/voices`

Expected: HTTP 200 JSON containing Yunxi, Yunze, and Xiaoxiao voice IDs.

- [ ] **Step 4: Perform browser UX and accessibility verification**

在 375px、768px、1024px、1440px 检查无横向滚动；仅用键盘完成文本、声音、参数、生成、播放、下载；检查键盘焦点、错误 `aria-live`、44px 目标、减少动画设置和生成中布局稳定性。记录并修复发现的问题后重跑 `python -m pytest -v`。

- [ ] **Step 5: Perform real Edge TTS smoke tests**

分别使用云希、云泽、晓晓生成短句，确认三份 MP3 可播放且非空；再用一篇 3,000–5,000 字中文文本验证进度、完整生成、播放和下载。断网重试一次，确认用户文案不包含内部异常。

- [ ] **Step 6: Inspect the final diff and commit documentation/fixes**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intended files remain before commit.

```bash
git add README.md .gitignore app static tests requirements.txt
git commit -m "docs: add local setup and verified usage"
```

- [ ] **Step 7: Request a whole-branch review**

Review against the spec with special attention to single-job concurrency, safe temporary-file handling, public error redaction, long-text progress, keyboard accessibility, and responsive behavior. Address findings, rerun the full test suite, and commit only verified fixes.
