/**
 * HTTP client for the local backend.
 *
 * Every rejection carries the backend's structured error (code / remedy /
 * action) so the UI can show the user what to do, not just that something
 * broke. Losing that detail is what made the previous version's failures
 * impossible to act on.
 */

const API_BASE = "http://127.0.0.1:9160/api";
const DEFAULT_TIMEOUT_MS = 20000;

/** Error with the backend's structured fields attached. */
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
}

async function request(path, { method = "GET", body, timeout = DEFAULT_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    // Abort and connection refused both land here; neither has a response.
    const offline = e.name === "AbortError"
      ? "バックエンドが応答しません（タイムアウト）"
      : "バックエンドに接続できません";
    throw new ApiError(offline, { code: "BACKEND_UNREACHABLE" });
  } finally {
    clearTimeout(timer);
  }

  if (res.ok) return res.json();

  const payload = await res.json().catch(() => ({}));
  // The backend returns its error object at the top level; FastAPI's own
  // errors (404, validation) nest a string under `detail`.
  const structured = payload.error_code ? payload : null;
  throw new ApiError(
    structured?.message || payload.detail || `リクエストに失敗しました (${res.status})`,
    {
      status: res.status,
      code: structured?.error_code || "",
      remedy: structured?.remedy || "",
      action: structured?.action || "",
      detail: structured?.detail || "",
      attempts: structured?.attempts || [],
    }
  );
}

const ApiClient = {
  ApiError,

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

// Reachable from both the popup (module-less script tag) and the content script.
if (typeof window !== "undefined") window.ApiClient = ApiClient;
