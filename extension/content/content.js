/**
 * In-page download button for YouTube watch pages.
 *
 * Three things make this survive YouTube's habit of changing:
 *   - The anchor is looked up through a list of candidate selectors, and if
 *     none match we do nothing at all. The toolbar popup keeps working, so a
 *     YouTube redesign degrades this feature instead of breaking the extension.
 *   - YouTube is a single-page app: navigating between videos never reloads the
 *     document, so we re-inject on `yt-navigate-finish` and on DOM mutations.
 *     The manifest matches all of youtube.com rather than just /watch, because
 *     Chrome only matches content scripts at document load — landing on the
 *     home page and clicking a video would otherwise inject nothing.
 *   - Backend calls go through the service worker (see lib/api-client.js): a
 *     content script's fetch carries the page origin, which the backend's CORS
 *     policy rejects.
 *
 * No YouTube internals are parsed here — only the page URL is read.
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

  // Identity token for the active progress loop. Replacing it makes any
  // in-flight `tick` stop; without it, a tick already awaiting a response when
  // the panel closes would schedule a fresh timer nothing can cancel, and keep
  // polling into a detached DOM node.
  let watchToken = null;

  const notify = (message) => chrome.runtime.sendMessage(message).catch(() => {});

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
    // Stop this panel's progress loop. The download itself keeps running in the
    // backend and stays listed as active, so the toolbar popup can pick it up.
    watchToken = null;
  }

  // === Panel ================================================================

  function buildPanel() {
    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "ytc-panel";

    const header = document.createElement("div");
    header.className = "ytc-panel-header";
    const heading = document.createElement("span");
    heading.textContent = "YouTube Chushutu";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "ytc-close";
    close.textContent = "×";
    close.addEventListener("click", removePanel);
    header.append(heading, close);

    const body = document.createElement("div");
    body.className = "ytc-body";
    const loading = document.createElement("p");
    loading.className = "ytc-muted";
    loading.textContent = "動画情報を取得中...";
    body.appendChild(loading);

    panel.append(header, body);
    return { panel, body };
  }

  function showMessage(body, message, remedy = "") {
    body.replaceChildren();
    const primary = document.createElement("p");
    primary.className = "ytc-error";
    primary.textContent = message;
    body.appendChild(primary);
    if (remedy) {
      const hint = document.createElement("p");
      hint.className = "ytc-muted";
      hint.textContent = remedy;
      body.appendChild(hint);
    }
  }

  async function togglePanel() {
    if (document.getElementById(PANEL_ID)) {
      removePanel();
      return;
    }

    const { panel, body } = buildPanel();
    document.body.appendChild(panel);

    let health;
    try {
      health = await ApiClient.healthCheck();
    } catch (e) {
      showMessage(
        body,
        e.message || "バックエンドに接続できません。",
        e.remedy || "start.bat を実行してサーバーを起動してください。"
      );
      return;
    }

    try {
      const info = await ApiClient.getVideoInfo(location.href);
      renderForm(body, info, health);
    } catch (e) {
      showMessage(body, e.message, e.remedy);
    }
  }

  function renderForm(body, info, health) {
    body.replaceChildren();

    const title = document.createElement("p");
    title.className = "ytc-title";
    title.textContent = info.title;

    const modes = document.createElement("div");
    modes.className = "ytc-row";
    const radios = {};
    for (const [value, label] of [["video", "動画+音声"], ["audio", "音声のみ"]]) {
      const wrapper = document.createElement("label");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "ytc-mode";
      radio.value = value;
      radio.checked = value === "video";
      radios[value] = radio;
      wrapper.append(radio, document.createTextNode(` ${label}`));
      modes.appendChild(wrapper);
    }

    // Built with the DOM rather than an innerHTML template: format ids come
    // from the network and would otherwise be interpolated into an attribute.
    const formatSelect = document.createElement("select");
    formatSelect.className = "ytc-select ytc-format";
    formatSelect.appendChild(new Option("自動（最高画質）", ""));
    for (const fmt of info.formats.filter((f) => !f.is_audio_only)) {
      const blocked = fmt.needs_merge && !health.ffmpeg_available;
      const option = new Option(
        blocked ? `${fmt.quality_label} — ffmpegが必要` : fmt.quality_label,
        fmt.format_id
      );
      option.disabled = blocked;
      formatSelect.appendChild(option);
    }

    const audioSelect = document.createElement("select");
    audioSelect.className = "ytc-select ytc-audio";
    audioSelect.hidden = true;
    audioSelect.appendChild(new Option("M4A / AAC（変換なし）", "m4a"));
    const mp3 = new Option(
      health.ffmpeg_available ? "MP3" : "MP3（ffmpegが必要）",
      "mp3"
    );
    mp3.disabled = !health.ffmpeg_available;
    audioSelect.appendChild(mp3);

    for (const radio of Object.values(radios)) {
      radio.addEventListener("change", () => {
        const audio = radios.audio.checked;
        formatSelect.hidden = audio;
        audioSelect.hidden = !audio;
      });
    }

    const go = document.createElement("button");
    go.type = "button";
    go.className = "ytc-go";
    go.textContent = "ダウンロード";

    const status = document.createElement("p");
    status.className = "ytc-status";

    body.append(title, modes, formatSelect, audioSelect);
    if (!health.ffmpeg_available) {
      const warn = document.createElement("p");
      warn.className = "ytc-warn";
      warn.textContent = "ffmpegが無いため最高720p程度になります。";
      body.appendChild(warn);
    }
    body.append(go, status);

    go.addEventListener("click", () =>
      run({
        go,
        status,
        audio: radios.audio.checked,
        formatId: formatSelect.value,
        audioFormat: audioSelect.value,
      })
    );
  }

  async function run({ go, status, audio, formatId, audioFormat }) {
    go.disabled = true;
    status.className = "ytc-status";
    status.textContent = "開始しています...";

    try {
      const request = { url: location.href, audio_only: audio };
      if (audio) request.audio_format = audioFormat;
      else if (formatId) request.format_id = formatId;

      const { task_id } = await ApiClient.startDownload(request);
      notify({ type: "DOWNLOAD_STARTED", taskId: task_id, title: document.title });
      watch(task_id, { go, status });
    } catch (e) {
      status.className = "ytc-status ytc-error";
      status.textContent = `${e.message} ${e.remedy || ""}`.trim();
      go.disabled = false;
    }
  }

  function watch(taskId, { go, status }) {
    const token = {};
    watchToken = token;
    let failures = 0;

    const finish = (className, text) => {
      watchToken = null;
      status.className = `ytc-status ${className}`;
      status.textContent = text;
      go.disabled = false;
    };

    const tick = async () => {
      if (watchToken !== token) return;

      let task;
      try {
        task = await ApiClient.getProgress(taskId);
        failures = 0;
      } catch (e) {
        if (watchToken !== token) return;
        if (e.status === 404) {
          return finish("ytc-error", "進捗が取得できなくなりました（サーバーが再起動された可能性があります）。");
        }
        if (++failures >= 8) {
          return finish("ytc-error", `進捗が取得できなくなりました: ${e.message}`);
        }
        pollTimer(tick, 1000);
        return;
      }

      if (watchToken !== token) return;

      if (task.status === "done") {
        notify({ type: "DOWNLOAD_COMPLETED", taskId });
        const name = (task.file_path || "").split(/[\\/]/).pop();
        finish("ytc-ok", `完了: ${name}`);
        for (const warning of task.warnings || []) {
          status.textContent += `\n${warning}`;
        }
        return;
      }

      if (task.status === "error") {
        notify({ type: "DOWNLOAD_COMPLETED", taskId });
        return finish("ytc-error", `${task.error || "エラー"} ${task.remedy || ""}`.trim());
      }

      status.textContent =
        task.attempt_note ||
        `${task.percent?.toFixed(1) ?? 0}% ${task.speed || ""} ${task.eta ? "残り " + task.eta : ""}`.trim();
      pollTimer(tick, 700);
    };

    tick();
  }

  function pollTimer(fn, delay) {
    setTimeout(fn, delay);
  }

  // === Lifecycle ============================================================

  // SPA navigation: the document never reloads, so re-inject on YouTube's own
  // navigation event and whenever the actions row is re-rendered.
  document.addEventListener("yt-navigate-finish", () => {
    removePanel();
    setTimeout(inject, 300);
  });

  // YouTube mutates the DOM constantly, so coalesce bursts into one check.
  // inject() short-circuits on the pathname and an id lookup before running
  // any selector, so the steady-state cost is negligible.
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
