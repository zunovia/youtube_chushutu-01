/**
 * API client for communicating with the local Python backend.
 */

const API_BASE = "http://localhost:9160/api";

const ApiClient = {
  /**
   * Check if the backend is running.
   */
  async healthCheck() {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error("Backend not reachable");
    return res.json();
  },

  /**
   * Fetch video metadata and available formats.
   * @param {string} url - YouTube video URL
   */
  async getVideoInfo(url) {
    const res = await fetch(
      `${API_BASE}/info?url=${encodeURIComponent(url)}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to fetch video info");
    }
    return res.json();
  },

  /**
   * Start a download task.
   * @param {object} params
   * @param {string} params.url
   * @param {string|null} params.format_id
   * @param {boolean} params.audio_only
   * @param {string} params.audio_format - "mp3" or "m4a"
   */
  async startDownload({ url, format_id = null, audio_only = false, audio_format = "mp3" }) {
    const res = await fetch(`${API_BASE}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format_id, audio_only, audio_format }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to start download");
    }
    return res.json();
  },

  /**
   * Poll download progress.
   * @param {string} taskId
   */
  async getProgress(taskId) {
    const res = await fetch(`${API_BASE}/progress/${taskId}`);
    if (!res.ok) throw new Error("Failed to get progress");
    return res.json();
  },

  /**
   * Open a downloaded file in the OS file manager.
   * @param {string} filePath
   */
  async openFile(filePath) {
    const res = await fetch(`${API_BASE}/open-file`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: filePath }),
    });
    return res.json();
  },
};
