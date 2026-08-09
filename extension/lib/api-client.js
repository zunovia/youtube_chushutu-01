/**
 * HTTP client for the local backend.
 *
 * Runs in three contexts with different networking rules:
 *
 *   - Popup and service worker: origin is `chrome-extension://…`, which the
 *     backend's CORS policy allows, so they fetch directly.
 *   - Content script: despite `host_permissions`, a content script's fetch
 *     carries the *page's* origin (`https://www.youtube.com`). The backend
 *     rejects that, and Chrome's Private Network Access rules block an https
 *     page reaching 127.0.0.1 regardless. So content scripts relay every call
 *     through the service worker, which is the supported MV3 path.
 *
 * Every rejection carries the backend's structured error (code / remedy /
 * action) so the UI can tell the user what to do, not just that something
 * broke. Losing that detail is what made v1's failures impossible to act on.
 */

const DEFAULT_PORT = 9160;
const DEFAULT_TIMEOUT_MS = 20000;

// The backend port is configurable server-side via YTC_PORT, so the client has
// to be able to follow it. Cached after the first read; storage changes update
// it in every context that has this script loaded.
let cachedPort = null;

async function apiBase() {
  if (cachedPort === null) {
    try {
      const { backendPort } = await chrome.storage.local.get("backendPort");
      cachedPort = Number(backendPort) || DEFAULT_PORT;
    } catch {
      cachedPort = DEFAULT_PORT;
    }
  }
  return `http://127.0.0.1:${cachedPort}/api`;
}

chrome.storage?.onChanged?.addListener((changes, area) => {
  if (area === "local" && changes.backendPort) {
    cachedPort = Number(changes.backendPort.newValue) || DEFAULT_PORT;
  }
});

/** Error carrying the backend's structured fields. */
class ApiError extends Error {
  constructor(message, { status = 0, code = "", remedy = "", action = "", detail = "", attempts = [] } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.remedy = remedy;
    this.action = action;
    this.detail = detail;
    this.attempts = attempts;
  }

  /** Plain object form — Error instances do not survive chrome.runtime messaging. */
  toPlain() {
    const { message, status, code, remedy, action, detail, attempts } = this;
    return { message, status, code, remedy, action, detail, attempts };
  }

  static fromPlain(plain) {
    return new ApiError(plain?.message || "不明なエラー", plain || {});
  }
}

/** True when this script is running inside a page (content script). */
function isContentScript() {
  return typeof location !== "undefined" && location.protocol.startsWith("http");
}

/** Perform the request directly. Only valid from an extension-origin context. */
async function rawRequest(path, { method = "GET", body, timeout = DEFAULT_TIMEOUT_MS } = {}) {
  const base = await apiBase();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    let res;
    try {
      res = await fetch(`${base}${path}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (e) {
      // Abort and connection-refused both land here; neither has a response.
      throw new ApiError(
        e.name === "AbortError" ? "バックエンドが応答しません（タイムアウト）" : "バックエンドに接続できません",
        { code: "BACKEND_UNREACHABLE" }
      );
    }

    // Read the body inside the try so a truncated or non-JSON response becomes
    // an ApiError rather than a bare SyntaxError with no status attached, and
    // while the abort timer is still armed so a stalled body cannot hang us.
    let payload = null;
    try {
      const text = await res.text();
      payload = text ? JSON.parse(text) : null;
    } catch (e) {
      if (res.ok) {
        throw new ApiError("バックエンドの応答を解釈できませんでした。", {
          status: res.status,
          code: "BAD_RESPONSE",
          remedy: "サーバーを再起動してから、もう一度お試しください。",
          detail: String(e),
        });
      }
      payload = null; // fall through to the error path below
    }

    if (res.ok) return payload;

    // The backend returns its error object at the top level; FastAPI's own
    // errors (404, validation) nest a string under `detail`.
    const structured = payload?.error_code ? payload : null;
    throw new ApiError(
      structured?.message || payload?.detail || `リクエストに失敗しました (${res.status})`,
      {
        status: res.status,
        code: structured?.error_code || "",
        remedy: structured?.remedy || "",
        action: structured?.action || "",
        detail: structured?.detail || "",
        attempts: structured?.attempts || [],
      }
    );
  } finally {
    clearTimeout(timer);
  }
}

/** Route through the service worker, which can legally reach localhost. */
async function relayRequest(path, options = {}) {
  let reply;
  try {
    reply = await chrome.runtime.sendMessage({ type: "API_REQUEST", path, options });
  } catch {
    throw new ApiError("拡張機能と通信できませんでした。", {
      code: "EXTENSION_UNREACHABLE",
      remedy: "ページを再読み込みするか、拡張機能を読み込み直してください。",
    });
  }
  if (!reply) {
    throw new ApiError("拡張機能から応答がありませんでした。", { code: "EXTENSION_UNREACHABLE" });
  }
  if (reply.ok) return reply.data;
  throw ApiError.fromPlain(reply.error);
}

const request = (path, options) =>
  isContentScript() ? relayRequest(path, options) : rawRequest(path, options);

const ApiClient = {
  ApiError,
  rawRequest, // used by the service worker to service relayed calls

  /** Backend liveness plus ffmpeg / cookie availability. */
  healthCheck: () => request("/health", { timeout: 4000 }),

  /** Video metadata and formats. Slow: the retry chain runs behind this. */
  getVideoInfo: (url) => request(`/info?url=${encodeURIComponent(url)}`, { timeout: 90000 }),

  /** Queue a download. Resolves to { task_id }. */
  startDownload: ({ url, format_id = null, audio_only = false, audio_format = "mp3" }) =>
    request("/download", { method: "POST", body: { url, format_id, audio_only, audio_format } }),

  /** Poll progress. Throws with status 404 once the task is gone. */
  getProgress: (taskId) => request(`/progress/${taskId}`, { timeout: 8000 }),

  /** yt-dlp version status (cached 24h server-side). */
  checkUpdate: (force = false) => request(`/update-check?force=${force}`, { timeout: 10000 }),

  /** Run pip to upgrade yt-dlp. Slow. */
  applyUpdate: () => request("/update-ytdlp", { method: "POST", timeout: 300000 }),

  /** Everything needed to explain a breakage. */
  diagnostics: () => request("/diagnostics", { timeout: 8000 }),

  /** Reveal a finished file in the OS file manager. */
  openFile: (path) => request("/open-file", { method: "POST", body: { path } }),
};

// Reachable from the popup (window), the content script (window) and the
// service worker (no window, but globalThis works everywhere).
globalThis.ApiClient = ApiClient;
