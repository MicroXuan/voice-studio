const POLL_INTERVAL = 800;

const elements = {
  form: document.querySelector("#tts-form"),
  text: document.querySelector("#text-input"),
  characterCount: document.querySelector("#character-count"),
  voiceList: document.querySelector("#voice-list"),
  rate: document.querySelector("#rate"),
  pitch: document.querySelector("#pitch"),
  volume: document.querySelector("#volume"),
  rateValue: document.querySelector("#rate-value"),
  pitchValue: document.querySelector("#pitch-value"),
  volumeValue: document.querySelector("#volume-value"),
  resetControls: document.querySelector("#reset-controls"),
  clearText: document.querySelector("#clear-text"),
  generateButton: document.querySelector("#generate-button"),
  statusTitle: document.querySelector("#status-title"),
  statusMessage: document.querySelector("#status-message"),
  progressBar: document.querySelector("#progress-bar"),
  progressPercent: document.querySelector("#progress-percent"),
  waveform: document.querySelector("#waveform"),
  errorActions: document.querySelector("#error-actions"),
  audioResult: document.querySelector("#audio-result"),
  audioPlayer: document.querySelector("#audio-player"),
  downloadLink: document.querySelector("#download-link"),
};

let activeJobId = null;
let pollTimer = null;
let isBusy = false;

async function loadVoices() {
  try {
    const response = await fetch("/api/voices");
    if (!response.ok) {
      throw new Error("声音清单暂时不可用");
    }
    const voices = await response.json();
    renderVoiceChoices(voices);
    updateSubmitState();
  } catch (error) {
    elements.voiceList.querySelector(".voice-loading").innerHTML =
      "<span>声音加载失败，请重试。</span>";
    renderError("无法读取声音清单，请检查本地服务后重试。", loadVoices);
  }
}

function renderVoiceChoices(voices) {
  const legend = elements.voiceList.querySelector("legend");
  elements.voiceList.replaceChildren(legend);
  const choices = document.createElement("div");
  choices.className = "voice-choices";

  voices.forEach((voice, index) => {
    const label = document.createElement("label");
    label.className = "voice-choice";

    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "voice";
    radio.value = voice.id;
    radio.checked = index === 0;

    const copy = document.createElement("span");
    copy.className = "voice-copy";
    const name = document.createElement("strong");
    name.textContent = voice.name;
    const meta = document.createElement("small");
    meta.textContent = `${voice.gender} · ${voice.description}`;
    copy.append(name, meta);

    const indicator = document.createElement("span");
    indicator.className = "radio-indicator";
    indicator.setAttribute("aria-hidden", "true");
    label.append(radio, copy, indicator);
    choices.append(label);
  });

  elements.voiceList.append(choices);
}

function serializeRequest() {
  const selectedVoice = elements.form.querySelector('input[name="voice"]:checked');
  return {
    text: elements.text.value.trim(),
    voice: selectedVoice?.value ?? "",
    rate: Number(elements.rate.value),
    pitch: Number(elements.pitch.value),
    volume: Number(elements.volume.value),
  };
}

async function createJob(event) {
  event?.preventDefault();
  const payload = serializeRequest();
  if (!payload.text) {
    renderError("请输入需要转换成语音的文字。", () => elements.text.focus());
    return;
  }
  if (!payload.voice) {
    renderError("请选择一个声音后再生成。", loadVoices);
    return;
  }

  stopPolling();
  resetAudioResult();
  setBusy(true);
  renderStatus("正在创建任务", "正在准备文字与声音参数…", 0);

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    const job = await response.json();
    activeJobId = job.id;
    renderJob(job);
    pollJob(activeJobId);
  } catch (error) {
    setBusy(false);
    renderError(error.message || "无法创建任务，请重试。", createJob);
  }
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    const job = await response.json();
    renderJob(job);
    if (job.state === "queued" || job.state === "running") {
      pollTimer = window.setTimeout(() => pollJob(jobId), POLL_INTERVAL);
    }
  } catch (error) {
    renderError(
      error.message || "暂时无法查询生成进度，任务仍会保留。",
      () => pollJob(activeJobId),
      "继续查询",
    );
  }
}

function renderJob(job) {
  if (job.state === "queued") {
    setBusy(true);
    renderStatus("任务已排队", job.message, job.progress);
    return;
  }
  if (job.state === "running") {
    setBusy(true);
    renderStatus("正在生成语音", job.message, job.progress);
    return;
  }
  if (job.state === "completed") {
    stopPolling();
    setBusy(false);
    renderStatus("生成完成", "可以直接试听，也可以下载 MP3。", 100);
    elements.audioPlayer.src = job.audio_url;
    elements.downloadLink.href = `${job.audio_url}?download=true`;
    elements.audioResult.hidden = false;
    elements.audioPlayer.load();
    return;
  }

  stopPolling();
  setBusy(false);
  renderStatus("生成没有完成", job.error || job.message, job.progress);
  renderError(job.error || "生成失败，请重新尝试。", createJob, "重新生成");
}

function renderError(message, retryAction, actionLabel = "重试") {
  elements.statusTitle.textContent = "需要处理一下";
  elements.statusMessage.textContent = message;
  elements.errorActions.replaceChildren();
  const button = document.createElement("button");
  button.type = "button";
  button.className = "retry-button";
  button.textContent = actionLabel;
  button.addEventListener("click", retryAction, { once: true });
  elements.errorActions.append(button);
  elements.errorActions.hidden = false;
}

function resetControls() {
  elements.rate.value = "0";
  elements.pitch.value = "0";
  elements.volume.value = "0";
  updateControlLabels();
  elements.resetControls.classList.add("is-reset");
  window.setTimeout(() => elements.resetControls.classList.remove("is-reset"), 220);
}

function updateWaveform(progress) {
  const boundedProgress = Math.max(0, Math.min(100, Number(progress) || 0));
  elements.progressBar.setAttribute("aria-valuenow", String(progress));
  elements.progressBar.style.setProperty("--progress", `${progress}%`);
  elements.progressPercent.textContent = `${progress}%`;
  const bars = [...elements.waveform.querySelectorAll("i")];
  const activeBars = Math.round((boundedProgress / 100) * bars.length);
  bars.forEach((bar, index) => {
    const active = index < activeBars;
    bar.style.setProperty("--progress-scale", active ? "1" : "0.55");
    bar.style.setProperty("--bar-color", active ? "var(--signal)" : "var(--line)");
    bar.style.opacity = active ? "1" : "0.7";
  });
}

function renderStatus(title, message, progress) {
  elements.statusTitle.textContent = title;
  elements.statusMessage.textContent = message;
  elements.errorActions.hidden = true;
  updateWaveform(progress);
}

function updateCharacterCount() {
  const count = elements.text.value.length;
  elements.characterCount.textContent = `${count.toLocaleString("zh-CN")} / 20,000`;
  updateSubmitState();
}

function updateSubmitState() {
  const hasText = Boolean(elements.text.value.trim());
  const hasVoice = Boolean(elements.form.querySelector('input[name="voice"]:checked'));
  elements.generateButton.disabled = isBusy || !hasText || !hasVoice;
}

function updateControlLabels() {
  elements.rateValue.textContent = formatSigned(elements.rate.value, "%");
  elements.pitchValue.textContent = formatSigned(elements.pitch.value, "Hz");
  elements.volumeValue.textContent = formatSigned(elements.volume.value, "%");
}

function formatSigned(value, unit) {
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number}${unit}`;
}

function setBusy(busy) {
  isBusy = busy;
  elements.form.classList.toggle("is-busy", busy);
  elements.text.readOnly = busy;
  elements.form.querySelectorAll('input[type="radio"], input[type="range"]').forEach((control) => {
    control.disabled = busy;
  });
  elements.clearText.disabled = busy;
  elements.resetControls.disabled = busy;
  updateSubmitState();
}

function resetAudioResult() {
  elements.audioPlayer.pause();
  elements.audioPlayer.removeAttribute("src");
  elements.downloadLink.href = "#";
  elements.audioResult.hidden = true;
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function readError(response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch (_) {
    // Fall through to the stable public message.
  }
  return "请求没有完成，请检查输入后重试。";
}

elements.form.addEventListener("submit", createJob);
elements.text.addEventListener("input", updateCharacterCount);
elements.voiceList.addEventListener("change", updateSubmitState);
[elements.rate, elements.pitch, elements.volume].forEach((control) => {
  control.addEventListener("input", updateControlLabels);
});
elements.resetControls.addEventListener("click", resetControls);
elements.clearText.addEventListener("click", () => {
  elements.text.value = "";
  elements.text.focus();
  updateCharacterCount();
});
elements.audioPlayer.addEventListener("play", () => elements.waveform.classList.add("is-playing"));
elements.audioPlayer.addEventListener("pause", () => elements.waveform.classList.remove("is-playing"));
elements.audioPlayer.addEventListener("ended", () => elements.waveform.classList.remove("is-playing"));

updateCharacterCount();
updateControlLabels();
updateWaveform(0);
loadVoices();
