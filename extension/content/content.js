/**
 * In-page download button for YouTube watch pages.
 *
 * Two things make this survive YouTube's habit of changing:
 *   - The anchor is looked up through a list of candidate selectors, and if
 *     none match we simply do nothing. The toolbar popup keeps working, so a
 *     YouTube redesign degrades this feature instead of breaking the extension.
 *   - YouTube is a single-page app: navigating between videos never reloads the
 *     document, so we re-inject on `yt-navigate-finish` and on DOM mutations.
 *
 * No YouTube internals are parsed here — only the page URL is read. All
 * extraction happens in the backend.
 */

(() => {
  const BUTTON_ID = "ytc-download-button";
  const PANEL_ID = "ytc-panel";

  // Tried in order; the first one present wins.
  const ANCHORS = [
    "#top-level-buttons-computed",
    "ytd-watch-metadata #actions-inner #top-level-buttons-computed",
    "ytd-watch-metadata #actions",
    "#menu-container #top-level-buttons-computed",
  ];

  let pollTimer = null;

  // === Injection ============================================================

  function findAnchor() {
    for (const selector of ANCHORS) {
      const el = document.querySelector(selector);
      if (el) return el;
    }
    return null;
  }

  function inject() {
    if (!location.pathname.startsWith("/watch")) return;
    if (document.getElementById(BUTTON_ID)) return;

    const anchor = findAnchor();
    if (!anchor) return; // YouTube changed its layout — stay quiet.

    const button = document.createElement("button");
    button.id = BUTTON_ID;
    button.className = "ytc-btn";
    button.textContent = "↓ 保存";
    button.title = "YouTube Chushutu でダウンロード";
    button.addEventListener("click", togglePanel);
    anchor.appendChild(button);
  }

  function removePanel() {
    document.getElementById(PANEL_ID)?.remove();
    clearTimeout(pollTimer);
    pollTimer = null;
  }

  // === Panel ================================================================

  async function togglePanel() {
    if (document.getElementById(PANEL_ID)) {
      removePanel();
      return;
    }

    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "ytc-panel";
    panel.innerHTML = `
      <div class="ytc-panel-header">
        <span>YouTube Chushutu</span>
        <button class="ytc-close" type="button">&times;</button>
      </div>
      <div class="ytc-body"><p class="ytc-muted">動画情報を取得中...</p></div>
    `;
    document.body.appendChild(panel);
    panel.querySelector(".ytc-close").addEventListener("click", removePanel);

    const body = panel.querySelector(".ytc-body");

    let health;
    try {
      health = await ApiClient.healthCheck();
    } catch {
      body.innerHTML = `
        <p class="ytc-error">バックエンドに接続できません。</p>
        <p class="ytc-muted">start.bat を実行してサーバーを起動してください。</p>`;
      return;
    }

    try {
      const info = await ApiClient.getVideoInfo(location.href);
      renderForm(body, info, health);
    } catch (e) {
      body.innerHTML = `
        <p class="ytc-error"></p>
        <p class="ytc-muted"></p>`;
      body.querySelector(".ytc-error").textContent = e.message;
      body.querySelector(".ytc-muted").textContent = e.remedy || "";
    }
  }

  function renderForm(body, info, health) {
    const videoFormats = info.formats.filter((f) => !f.is_audio_only);
    const options = [
      '<option value="">自動（最高画質）</option>',
      ...videoFormats.map((f) => {
        const blocked = f.needs_merge && !health.ffmpeg_available;
        const label = blocked ? `${f.quality_label} — ffmpegが必要` : f.quality_label;
        return `<option value="${f.format_id}"${blocked ? " disabled" : ""}>${escapeHtml(label)}</option>`;
      }),
    ].join("");

    body.innerHTML = `
      <p class="ytc-title"></p>
      <div class="ytc-row">
        <label><input type="radio" name="ytc-mode" value="video" checked> 動画+音声</label>
        <label><input type="radio" name="ytc-mode" value="audio"> 音声のみ</label>
      </div>
      <select class="ytc-select ytc-format">${options}</select>
      <select class="ytc-select ytc-audio" hidden>
        <option value="m4a">M4A / AAC（変換なし）</option>
        <option value="mp3"${health.ffmpeg_available ? "" : " disabled"}>MP3${health.ffmpeg_available ? "" : "（ffmpegが必要）"}</option>
      </select>
      ${health.ffmpeg_available ? "" : '<p class="ytc-warn">ffmpegが無いため最高720p程度になります。</p>'}
      <button class="ytc-go" type="button">ダウンロード</button>
      <p class="ytc-status"></p>
    `;
    body.querySelector(".ytc-title").textContent = info.title;

    const formatSelect = body.querySelector(".ytc-format");
    const audioSelect = body.querySelector(".ytc-audio");
    body.querySelectorAll('input[name="ytc-mode"]').forEach((radio) => {
      radio.addEventListener("change", () => {
        const audio = radio.value === "audio" && radio.checked;
        formatSelect.hidden = audio;
        audioSelect.hidden = !audio;
      });
    });

    body.querySelector(".ytc-go").addEventListener("click", () =>
      run(body, {
        audio: body.querySelector('input[name="ytc-mode"]:checked').value === "audio",
        formatId: formatSelect.value,
        audioFormat: audioSelect.value,
      })
    );
  }

  async function run(body, { audio, formatId, audioFormat }) {
    const button = body.querySelector(".ytc-go");
    const status = body.querySelector(".ytc-status");
    button.disabled = true;
    status.className = "ytc-status";
    status.textContent = "開始しています...";

    try {
      const request = { url: location.href, audio_only: audio };
      if (audio) request.audio_format = audioFormat;
      else if (formatId) request.format_id = formatId;

      const { task_id } = await ApiClient.startDownload(request);
      chrome.runtime.sendMessage({ type: "DOWNLOAD_STARTED", taskId: task_id, title: document.title });
      watch(task_id, body);
    } catch (e) {
      status.className = "ytc-status ytc-error";
      status.textContent = `${e.message} ${e.remedy || ""}`.trim();
      button.disabled = false;
    }
  }

  function watch(taskId, body) {
    const button = body.querySelector(".ytc-go");
    const status = body.querySelector(".ytc-status");
    let failures = 0;

    const tick = async () => {
      let task;
      try {
        task = await ApiClient.getProgress(taskId);
        failures = 0;
      } catch (e) {
        if (e.status === 404 || ++failures >= 8) {
          status.className = "ytc-status ytc-error";
          status.textContent = "進捗が取得できなくなりました。サーバーを確認してください。";
          button.disabled = false;
          return;
        }
        pollTimer = setTimeout(tick, 1000);
        return;
      }

      if (task.status === "done") {
        chrome.runtime.sendMessage({ type: "DOWNLOAD_COMPLETED", taskId });
        status.className = "ytc-status ytc-ok";
        status.textContent = `完了: ${(task.file_path || "").split(/[\\/]/).pop()}`;
        button.disabled = false;
        return;
      }

      if (task.status === "error") {
        chrome.runtime.sendMessage({ type: "DOWNLOAD_COMPLETED", taskId });
        status.className = "ytc-status ytc-error";
        status.textContent = `${task.error || "エラー"} ${task.remedy || ""}`.trim();
        button.disabled = false;
        return;
      }

      status.textContent =
        task.attempt_note ||
        `${task.percent?.toFixed(1) ?? 0}% ${task.speed || ""} ${task.eta ? "残り " + task.eta : ""}`.trim();
      pollTimer = setTimeout(tick, 700);
    };

    tick();
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // === Lifecycle ============================================================

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "GET_PAGE_URL") {
      sendResponse({ url: location.href });
    }
    return false;
  });

  // SPA navigation: the document never reloads, so re-inject on YouTube's own
  // navigation event and whenever the actions row is re-rendered.
  document.addEventListener("yt-navigate-finish", () => {
    removePanel();
    setTimeout(inject, 300);
  });

  // YouTube mutates the DOM constantly, so coalesce bursts into one check.
  let injectTimer = null;
  const observer = new MutationObserver(() => {
    if (injectTimer) return;
    injectTimer = setTimeout(() => {
      injectTimer = null;
      inject();
    }, 250);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  inject();
})();
