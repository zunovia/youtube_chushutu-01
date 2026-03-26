/**
 * Popup UI logic — handles video info display, format selection, and download progress.
 */

// DOM elements
const $ = (id) => document.getElementById(id);

const els = {
  statusDot: $("status-dot"),
  errorSection: $("error-section"),
  errorMessage: $("error-message"),
  notYoutube: $("not-youtube"),
  loading: $("loading"),
  videoInfo: $("video-info"),
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
  progressSection: $("progress-section"),
  progressStatus: $("progress-status"),
  progressPercent: $("progress-percent"),
  progressBar: $("progress-bar"),
  progressSpeed: $("progress-speed"),
  progressEta: $("progress-eta"),
  doneSection: $("done-section"),
  openFileBtn: $("open-file-btn"),
  newDownloadBtn: $("new-download-btn"),
};

// State
let currentUrl = null;
let currentMode = "video"; // "video" or "audio"
let currentTaskId = null;
let pollInterval = null;
let lastFilePath = null;

// === Initialization ===

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupButtons();
  await init();
});

async function init() {
  // Check backend health
  try {
    const health = await ApiClient.healthCheck();
    els.statusDot.classList.remove("offline");
    els.statusDot.classList.add("online");
    els.statusDot.title = `Backend online (yt-dlp ${health.yt_dlp_version})`;

    if (!health.ffmpeg_available) {
      showError("ffmpegが見つかりません。音声変換にはffmpegが必要です。");
    }
  } catch {
    els.statusDot.classList.remove("online");
    els.statusDot.classList.add("offline");
    els.statusDot.title = "Backend offline";
    showError("バックエンドに接続できません。サーバーを起動してください。");
    return;
  }

  // Check if we have active downloads from service worker
  try {
    const response = await chrome.runtime.sendMessage({ type: "GET_ACTIVE_DOWNLOADS" });
    const downloads = response?.downloads || {};
    const taskIds = Object.keys(downloads);
    if (taskIds.length > 0) {
      // Resume watching the most recent download
      currentTaskId = taskIds[taskIds.length - 1];
      showProgress();
      startPolling();
      return;
    }
  } catch {
    // No active downloads or service worker not ready
  }

  // Get current tab URL
  try {
    const response = await chrome.runtime.sendMessage({ type: "GET_VIDEO_URL" });
    if (response?.url) {
      currentUrl = response.url;
      await loadVideoInfo(currentUrl);
    } else {
      showSection("notYoutube");
    }
  } catch {
    showSection("notYoutube");
  }
}

// === UI Helpers ===

function showSection(name) {
  // Hide all sections
  els.errorSection.classList.add("hidden");
  els.notYoutube.classList.add("hidden");
  els.loading.classList.add("hidden");
  els.videoInfo.classList.add("hidden");
  els.progressSection.classList.add("hidden");
  els.doneSection.classList.add("hidden");

  // Show the requested one
  switch (name) {
    case "notYoutube": els.notYoutube.classList.remove("hidden"); break;
    case "loading": els.loading.classList.remove("hidden"); break;
    case "videoInfo": els.videoInfo.classList.remove("hidden"); break;
    case "progress": els.progressSection.classList.remove("hidden"); break;
    case "done": els.doneSection.classList.remove("hidden"); break;
  }
}

function showError(msg) {
  els.errorMessage.textContent = msg;
  els.errorSection.classList.remove("hidden");
}

function hideError() {
  els.errorSection.classList.add("hidden");
}

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

// === Video Info ===

async function loadVideoInfo(url) {
  showSection("loading");
  hideError();

  try {
    const info = await ApiClient.getVideoInfo(url);
    displayVideoInfo(info);
    showSection("videoInfo");
  } catch (e) {
    showSection("notYoutube");
    showError(`動画情報の取得に失敗しました: ${e.message}`);
  }
}

function displayVideoInfo(info) {
  els.thumbnail.src = info.thumbnail_url;
  els.videoTitle.textContent = info.title;
  els.duration.textContent = formatDuration(info.duration_seconds);
  els.channel.textContent = info.channel;

  // Populate video format dropdown
  const videoFormats = info.formats.filter((f) => !f.is_audio_only);
  els.formatSelect.innerHTML = "";

  if (videoFormats.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "自動 (最高画質)";
    els.formatSelect.appendChild(opt);
  } else {
    // Add "auto best" option
    const autOpt = document.createElement("option");
    autOpt.value = "";
    autOpt.textContent = "自動 (最高画質)";
    els.formatSelect.appendChild(autOpt);

    for (const fmt of videoFormats) {
      const opt = document.createElement("option");
      opt.value = fmt.format_id;
      opt.textContent = fmt.quality_label;
      els.formatSelect.appendChild(opt);
    }
  }
}

// === Tabs ===

function setupTabs() {
  els.tabVideo.addEventListener("click", () => {
    currentMode = "video";
    els.tabVideo.classList.add("active");
    els.tabAudio.classList.remove("active");
    els.videoOptions.classList.remove("hidden");
    els.audioOptions.classList.add("hidden");
  });

  els.tabAudio.addEventListener("click", () => {
    currentMode = "audio";
    els.tabAudio.classList.add("active");
    els.tabVideo.classList.remove("active");
    els.videoOptions.classList.add("hidden");
    els.audioOptions.classList.remove("hidden");
  });
}

// === Buttons ===

function setupButtons() {
  els.downloadBtn.addEventListener("click", startDownload);
  els.openFileBtn.addEventListener("click", openFile);
  els.newDownloadBtn.addEventListener("click", () => {
    lastFilePath = null;
    if (currentUrl) {
      loadVideoInfo(currentUrl);
    }
  });
}

// === Download ===

async function startDownload() {
  if (!currentUrl) return;

  els.downloadBtn.disabled = true;
  hideError();

  try {
    const params = {
      url: currentUrl,
      audio_only: currentMode === "audio",
    };

    if (currentMode === "video") {
      const formatId = els.formatSelect.value;
      if (formatId) params.format_id = formatId;
    } else {
      params.audio_format = els.audioFormatSelect.value;
    }

    const result = await ApiClient.startDownload(params);
    currentTaskId = result.task_id;

    // Notify service worker
    try {
      await chrome.runtime.sendMessage({
        type: "DOWNLOAD_STARTED",
        taskId: currentTaskId,
        title: els.videoTitle.textContent,
      });
    } catch {
      // Service worker might not be ready
    }

    showProgress();
    startPolling();
  } catch (e) {
    showError(`ダウンロード開始に失敗: ${e.message}`);
    els.downloadBtn.disabled = false;
  }
}

function showProgress() {
  showSection("progress");
  els.progressStatus.textContent = "ダウンロード中...";
  els.progressPercent.textContent = "0%";
  els.progressBar.style.width = "0%";
  els.progressSpeed.textContent = "";
  els.progressEta.textContent = "";
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    if (!currentTaskId) return;

    try {
      const task = await ApiClient.getProgress(currentTaskId);
      updateProgress(task);

      if (task.status === "done" || task.status === "error") {
        clearInterval(pollInterval);
        pollInterval = null;

        // Notify service worker
        try {
          await chrome.runtime.sendMessage({
            type: "DOWNLOAD_COMPLETED",
            taskId: currentTaskId,
          });
        } catch {
          // Ignore
        }

        if (task.status === "done") {
          lastFilePath = task.file_path;
          showSection("done");
        } else {
          showError(`エラー: ${task.error || "不明なエラー"}`);
          els.downloadBtn.disabled = false;
          showSection("videoInfo");
        }
      }
    } catch {
      // Backend might be temporarily unreachable, keep polling
    }
  }, 500);
}

function updateProgress(task) {
  const statusMap = {
    pending: "準備中...",
    downloading: "ダウンロード中...",
    converting: "変換中...",
    done: "完了!",
    error: "エラー",
  };

  els.progressStatus.textContent = statusMap[task.status] || task.status;
  els.progressPercent.textContent = `${task.percent.toFixed(1)}%`;
  els.progressBar.style.width = `${task.percent}%`;
  els.progressSpeed.textContent = task.speed || "";
  els.progressEta.textContent = task.eta ? `残り ${task.eta}` : "";
}

// === Open File ===

async function openFile() {
  if (!lastFilePath) return;
  try {
    await ApiClient.openFile(lastFilePath);
  } catch {
    showError("ファイルを開けませんでした");
  }
}
