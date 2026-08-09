/**
 * Popup UI.
 *
 * The rule that matters here: banners (error / warning / update) are never
 * touched by section switching. In v1 `showSection()` began by hiding the
 * error box, so every failure message was erased microseconds after being
 * shown and downloads appeared to fail silently.
 *
 * The second rule, learned from the same incident: a message the user can see
 * must come with something they can *do*. Every error carries a remedy, and if
 * it offers a button that button must actually work in the state it appears in.
 */

const $ = (id) => document.getElementById(id);

const els = {
  statusDot: $("status-dot"),
  diagnosticsBtn: $("diagnostics-btn"),

  updateBanner: $("update-banner"),
  updateText: $("update-text"),
  updateBtn: $("update-btn"),
  updateDismiss: $("update-dismiss"),

  warningBanner: $("warning-banner"),
  warningText: $("warning-text"),

  errorBanner: $("error-banner"),
  errorText: $("error-text"),
  errorRemedy: $("error-remedy"),
  errorAction: $("error-action"),
  errorDismiss: $("error-dismiss"),
  errorDetails: $("error-details"),
  errorDetailText: $("error-detail-text"),

  loadingText: $("loading-text"),
  thumbnail: $("thumbnail"),
  videoTitle: $("video-title"),
  duration: $("duration"),
  channel: $("channel"),
  tabVideo: $("tab-video"),
  tabAudio: $("tab-audio"),
  videoOptions: $("video-options"),
  audioOptions: $("audio-options"),
  formatSelect: $("format-select"),
  audioFormatSelect: $("audio-format-select"),
  downloadBtn: $("download-btn"),

  progressStatus: $("progress-status"),
  progressPercent: $("progress-percent"),
  progressBar: $("progress-bar"),
  progressSpeed: $("progress-speed"),
  progressEta: $("progress-eta"),
  retryNote: $("retry-note"),

  doneFilename: $("done-filename"),
  openFileBtn: $("open-file-btn"),
  newDownloadBtn: $("new-download-btn"),

  diagnosticsText: $("diagnostics-text"),
  diagnosticsCopy: $("diagnostics-copy"),
  diagnosticsClose: $("diagnostics-close"),
  portInput: $("port-input"),
  portSave: $("port-save"),
};

const SECTIONS = [
  "not-youtube",
  "loading",
  "video-info",
  "progress-section",
  "done-section",
  "diagnostics-section",
];

const STATUS_LABEL = {
  pending: "準備中...",
  downloading: "ダウンロード中...",
  converting: "変換中...",
  done: "完了",
  error: "エラー",
};

// Buttons a remedy can offer. Declared before showError() uses it, so no code
// path can hit the temporal dead zone inside the very function whose job is
// to report errors.
const ACTION_LABELS = {
  update_ytdlp: "yt-dlpを更新",
  install_ffmpeg: "インストール手順を見る",
  login_youtube: "YouTubeを開く",
  choose_auto_format: "自動画質でやり直す",
  retry: "もう一度試す",
  open_diagnostics: "診断情報を見る",
};

const FFMPEG_WARNING =
  "ffmpegが見つかりません。MP3変換と高画質（1080p以上）の保存にはffmpegが必要です。" +
  "この状態でも720p程度までは保存できます。";

const state = {
  url: null,
  mode: "video",
  taskId: null,
  filePath: null,
  health: null,
  pollTimer: null,
  pollFailures: 0,
  warnings: [],
  // Which stage failed, so "もう一度試す" retries the right thing.
  failedStage: null, // "info" | "download" | null
};

// === Section / banner plumbing ==============================================

/** Show exactly one section. Deliberately leaves all banners alone. */
function showSection(id) {
  for (const name of SECTIONS) {
    $(name).classList.toggle("hidden", name !== id);
  }
}

function clearBanners() {
  els.errorBanner.classList.add("hidden");
  els.warningBanner.classList.add("hidden");
  state.warnings = [];
}

function showError(message, { remedy = "", action = "", detail = "", attempts = [] } = {}) {
  els.errorText.textContent = message;
  els.errorRemedy.textContent = remedy;
  els.errorRemedy.classList.toggle("hidden", !remedy);

  const label = ACTION_LABELS[action];
  els.errorAction.classList.toggle("hidden", !label);
  if (label) {
    els.errorAction.textContent = label;
    els.errorAction.onclick = () => runAction(action);
  }

  const trail = attempts.length ? `\n\n試した方法:\n- ${attempts.join("\n- ")}` : "";
  els.errorDetailText.textContent = (detail || "") + trail;
  els.errorDetails.classList.toggle("hidden", !detail && !trail);

  els.errorBanner.classList.remove("hidden");
}

/** Warnings accumulate — a second one must not erase the first. */
function showWarning(message) {
  if (!message || state.warnings.includes(message)) return;
  state.warnings.push(message);
  els.warningText.textContent = state.warnings.join("\n\n");
  els.warningBanner.classList.remove("hidden");
}

function warnIfNoFfmpeg() {
  if (state.health && !state.health.ffmpeg_available) showWarning(FFMPEG_WARNING);
}

// === Remedy buttons =========================================================

async function runAction(action) {
  switch (action) {
    case "update_ytdlp":
      await applyUpdate();
      break;
    case "install_ffmpeg":
      chrome.tabs.create({ url: "https://www.gyan.dev/ffmpeg/builds/" });
      break;
    case "login_youtube":
      chrome.tabs.create({ url: "https://www.youtube.com/" });
      break;
    case "choose_auto_format":
      els.formatSelect.value = "";
      clearBanners();
      warnIfNoFfmpeg();
      startDownload();
      break;
    case "retry":
      clearBanners();
      warnIfNoFfmpeg();
      // Retrying a download when it was the metadata fetch that failed would
      // start a download of a video the user was never shown.
      if (state.failedStage === "info") loadVideoInfo(state.url);
      else startDownload();
      break;
    case "open_diagnostics":
      await showDiagnostics();
      break;
  }
}

// === Startup ================================================================

document.addEventListener("DOMContentLoaded", async () => {
  wireEvents();
  await init();
});

async function init() {
  try {
    state.health = await ApiClient.healthCheck();
    els.statusDot.classList.replace("offline", "online");
    els.statusDot.title = `接続済み (yt-dlp ${state.health.yt_dlp_version})`;
  } catch {
    els.statusDot.title = "バックエンド未接続";
    showSection("not-youtube");
    showError("バックエンドに接続できません。", {
      remedy: "start.bat（Windows）または start.sh を実行してサーバーを起動してください。",
      action: "retry",
    });
    return;
  }

  // Persistent, because it explains a whole class of download failures.
  warnIfNoFfmpeg();
  checkForUpdate(); // fire and forget — must never delay the UI

  // Resolve the tab URL first: a resumed download can still fail, and the
  // error path drops the user on the video-info section, which is useless
  // (and its retry button dead) if we never loaded the video.
  let tab;
  try {
    tab = await sendMessage({ type: "GET_VIDEO_URL" });
  } catch {
    showSection("not-youtube");
    showError("拡張機能の内部通信に失敗しました。", {
      remedy: "ページを再読み込みするか、chrome://extensions で拡張機能を再読み込みしてください。",
    });
    return;
  }
  state.url = tab?.url || null;

  // A download may still be running from a previous popup session.
  const active = await sendMessage({ type: "GET_ACTIVE_DOWNLOADS" }).catch(() => null);
  const ids = Object.keys(active?.downloads || {});
  if (ids.length) {
    state.taskId = ids[ids.length - 1];
    showSection("progress-section");
    if (state.url) loadVideoInfo(state.url, { silent: true });
    poll();
    return;
  }

  if (!state.url) {
    showSection("not-youtube");
    return;
  }
  await loadVideoInfo(state.url);
}

/** Reject (rather than resolve null) when the worker cannot be reached. */
function sendMessage(message) {
  return chrome.runtime.sendMessage(message);
}

// === Video info =============================================================

/**
 * @param {object} [opts]
 * @param {boolean} [opts.silent] Populate the form without taking over the
 *   view — used to back-fill the video info while a resumed download runs.
 */
async function loadVideoInfo(url, { silent = false } = {}) {
  if (!url) return;
  if (!silent) {
    showSection("loading");
    els.loadingText.textContent = "動画情報を取得中...";
    clearBanners();
    warnIfNoFfmpeg();
  }

  try {
    const info = await ApiClient.getVideoInfo(url);
    renderVideoInfo(info);
    state.failedStage = null;
    if (!silent) showSection("video-info");
  } catch (e) {
    // A silent load must not clobber the banner explaining a download failure.
    if (silent) return;
    state.failedStage = "info";
    showSection("not-youtube");
    showError(e.message, {
      remedy: e.remedy,
      action: e.action || "retry",
      detail: e.detail,
      attempts: e.attempts,
    });
  }
}

function renderVideoInfo(info) {
  if (info.thumbnail_url) els.thumbnail.src = info.thumbnail_url;
  else els.thumbnail.removeAttribute("src");
  els.videoTitle.textContent = info.title;
  els.duration.textContent = formatDuration(info.duration_seconds);
  els.channel.textContent = info.channel;

  const hasFfmpeg = Boolean(state.health?.ffmpeg_available);
  els.formatSelect.innerHTML = "";
  els.formatSelect.appendChild(new Option("自動（最高画質）", ""));

  for (const fmt of info.formats.filter((f) => !f.is_audio_only)) {
    // Video-only streams have to be muxed with audio, which needs ffmpeg.
    // Offering them without it would produce a silent file.
    const blocked = fmt.needs_merge && !hasFfmpeg;
    const option = new Option(
      blocked ? `${fmt.quality_label} — ffmpegが必要` : fmt.quality_label,
      fmt.format_id
    );
    option.disabled = blocked;
    els.formatSelect.appendChild(option);
  }

  const mp3Option = els.audioFormatSelect.querySelector('option[value="mp3"]');
  mp3Option.disabled = !hasFfmpeg;
  if (!hasFfmpeg) els.audioFormatSelect.value = "m4a";
}

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

// === Download ===============================================================

async function startDownload() {
  if (!state.url) {
    showError("動画のURLを取得できませんでした。", {
      remedy: "YouTubeの動画ページを開いた状態で、拡張機能のアイコンをクリックしてください。",
    });
    els.downloadBtn.disabled = false;
    return;
  }

  els.downloadBtn.disabled = true;
  clearBanners();
  warnIfNoFfmpeg();

  const request = { url: state.url, audio_only: state.mode === "audio" };
  if (state.mode === "video") {
    if (els.formatSelect.value) request.format_id = els.formatSelect.value;
  } else {
    request.audio_format = els.audioFormatSelect.value;
  }

  try {
    const { task_id } = await ApiClient.startDownload(request);
    state.taskId = task_id;
    state.pollFailures = 0;
    state.failedStage = null;
    sendMessage({
      type: "DOWNLOAD_STARTED",
      taskId: task_id,
      title: els.videoTitle.textContent,
    }).catch(() => {});

    resetProgress();
    showSection("progress-section");
    poll();
  } catch (e) {
    state.failedStage = "download";
    showSection("video-info");
    showError(e.message, { remedy: e.remedy, action: e.action, detail: e.detail });
    els.downloadBtn.disabled = false;
  }
}

function resetProgress() {
  els.progressStatus.textContent = "準備中...";
  els.progressPercent.textContent = "0%";
  els.progressBar.style.width = "0%";
  els.progressSpeed.textContent = "";
  els.progressEta.textContent = "";
  els.retryNote.classList.add("hidden");
}

function finishTask() {
  clearTimeout(state.pollTimer);
  state.pollTimer = null;
  if (state.taskId) {
    sendMessage({ type: "DOWNLOAD_COMPLETED", taskId: state.taskId }).catch(() => {});
  }
  state.taskId = null;
  els.downloadBtn.disabled = false;
}

/** Poll progress on a timeout chain, so a slow backend cannot pile up requests. */
async function poll() {
  if (!state.taskId) return;

  let task;
  try {
    task = await ApiClient.getProgress(state.taskId);
    state.pollFailures = 0;
  } catch (e) {
    // 404 means the task is gone for good — almost always a server restart.
    // Retrying forever (as v1 did) just leaves the spinner turning.
    if (e.status === 404) {
      return stopPolling(
        "ダウンロードの進捗が分からなくなりました。",
        "サーバーが再起動された可能性があります。もう一度ダウンロードしてください。"
      );
    }

    state.pollFailures += 1;
    if (state.pollFailures >= 8) {
      return stopPolling(
        `バックエンドと通信できなくなりました（${e.message}）。`,
        "サーバーが動いているか確認してから、もう一度お試しください。"
      );
    }
    state.pollTimer = setTimeout(poll, Math.min(500 * state.pollFailures, 3000));
    return;
  }

  renderProgress(task);

  if (task.status === "done") {
    finishTask();
    state.filePath = task.file_path;
    els.doneFilename.textContent = (task.file_path || "").split(/[\\/]/).pop();
    showSection("done-section");
    for (const warning of task.warnings || []) showWarning(warning);
    return;
  }

  if (task.status === "error") {
    finishTask();
    state.failedStage = "download";
    // showSection no longer clears banners, but switching first and showing
    // second keeps the intent obvious.
    showSection("video-info");
    showError(task.error || "不明なエラーが発生しました。", {
      remedy: task.remedy,
      action: task.action,
      detail: task.error_detail,
      attempts: task.attempts,
    });
    return;
  }

  state.pollTimer = setTimeout(poll, 500);
}

function stopPolling(message, remedy) {
  finishTask();
  state.failedStage = "download";
  showSection("video-info");
  showError(message, { remedy, action: "retry" });
}

function renderProgress(task) {
  els.progressStatus.textContent = STATUS_LABEL[task.status] || task.status;
  els.progressPercent.textContent = `${(task.percent ?? 0).toFixed(1)}%`;
  els.progressBar.style.width = `${task.percent ?? 0}%`;
  els.progressSpeed.textContent = task.speed || "";
  els.progressEta.textContent = task.eta ? `残り ${task.eta}` : "";

  els.retryNote.textContent = task.attempt_note || "";
  els.retryNote.classList.toggle("hidden", !task.attempt_note);
}

// === Updates ================================================================

async function checkForUpdate() {
  try {
    const info = await ApiClient.checkUpdate();
    if (!info.update_available) return;

    const { updateDismissedUntil = 0 } = await chrome.storage.local.get("updateDismissedUntil");
    if (Date.now() < updateDismissedUntil) return;

    els.updateText.textContent = `yt-dlpの更新があります（${info.current} → ${info.latest}）`;
    els.updateBanner.classList.remove("hidden");
  } catch {
    // Offline is normal; never bother the user about a failed update check.
  }
}

async function applyUpdate() {
  els.updateBtn.disabled = true;
  els.updateBtn.textContent = "更新中...";
  try {
    const result = await ApiClient.applyUpdate();
    els.updateText.textContent = result.note || "更新しました。";
    els.updateBanner.classList.remove("hidden");
    els.updateBtn.classList.add("hidden");
    els.updateDismiss.textContent = "閉じる";
  } catch (e) {
    els.updateText.textContent = `更新に失敗しました: ${e.message}`;
    els.updateBtn.disabled = false;
    els.updateBtn.textContent = "更新する";
  }
}

// === Diagnostics ============================================================

async function showDiagnostics() {
  showSection("diagnostics-section");
  els.diagnosticsText.textContent = "読み込み中...";

  // Kept in sync with YTC_PORT on the server side; without this the extension
  // could never reach a backend started on a non-default port.
  const { backendPort = 9160 } = await chrome.storage.local.get("backendPort");
  els.portInput.value = backendPort;

  try {
    const d = await ApiClient.diagnostics();
    const lines = [
      `yt-dlp        : ${d.yt_dlp_version}`,
      `ffmpeg        : ${d.ffmpeg_available ? d.ffmpeg_path : "未インストール"}`,
      `Cookie取得元  : ${d.cookie_browser}`,
      `保存先        : ${d.download_dir}`,
      `Python        : ${d.python_version}`,
      `OS            : ${d.platform}`,
      "",
      "--- 直近のエラー ---",
    ];
    if (!d.recent_errors.length) {
      lines.push("なし");
    } else {
      for (const e of d.recent_errors) {
        lines.push(`[${e.at}] ${e.code}`, `  ${e.raw}`, "");
      }
    }
    els.diagnosticsText.textContent = lines.join("\n");
  } catch (e) {
    els.diagnosticsText.textContent = `診断情報を取得できません: ${e.message}`;
  }
}

// === Events =================================================================

function wireEvents() {
  els.tabVideo.addEventListener("click", () => setMode("video"));
  els.tabAudio.addEventListener("click", () => setMode("audio"));

  els.downloadBtn.addEventListener("click", startDownload);

  els.openFileBtn.addEventListener("click", async () => {
    if (!state.filePath) return;
    try {
      await ApiClient.openFile(state.filePath);
    } catch (e) {
      showError("保存先を開けませんでした。", { remedy: e.message });
    }
  });

  els.newDownloadBtn.addEventListener("click", () => {
    state.filePath = null;
    clearBanners();
    warnIfNoFfmpeg();
    if (state.url) loadVideoInfo(state.url);
    else showSection("not-youtube");
  });

  els.errorDismiss.addEventListener("click", () => els.errorBanner.classList.add("hidden"));
  els.updateBtn.addEventListener("click", applyUpdate);
  els.updateDismiss.addEventListener("click", async () => {
    els.updateBanner.classList.add("hidden");
    await chrome.storage.local.set({ updateDismissedUntil: Date.now() + 24 * 3600 * 1000 });
  });

  els.diagnosticsBtn.addEventListener("click", showDiagnostics);
  els.diagnosticsClose.addEventListener("click", () => {
    showSection(state.url ? "video-info" : "not-youtube");
  });
  els.portSave.addEventListener("click", async () => {
    const port = Number(els.portInput.value);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      showError("ポート番号が正しくありません。", { remedy: "1〜65535 の数値を入力してください。" });
      return;
    }
    await chrome.storage.local.set({ backendPort: port });
    els.portSave.textContent = "保存しました";
    setTimeout(() => (els.portSave.textContent = "保存"), 1500);
    state.health = null;
    await showDiagnostics();
  });

  els.diagnosticsCopy.addEventListener("click", () => {
    navigator.clipboard.writeText(els.diagnosticsText.textContent);
    els.diagnosticsCopy.textContent = "コピーしました";
    setTimeout(() => (els.diagnosticsCopy.textContent = "コピー"), 1500);
  });

  window.addEventListener("pagehide", () => clearTimeout(state.pollTimer));
}

function setMode(mode) {
  state.mode = mode;
  els.tabVideo.classList.toggle("active", mode === "video");
  els.tabAudio.classList.toggle("active", mode === "audio");
  els.videoOptions.classList.toggle("hidden", mode !== "video");
  els.audioOptions.classList.toggle("hidden", mode === "video");
}
