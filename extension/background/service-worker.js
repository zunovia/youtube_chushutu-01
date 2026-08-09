/**
 * MV3 service worker.
 *
 * Two jobs:
 *
 *  1. Relay backend calls for content scripts. A content script's fetch carries
 *     the page origin (https://www.youtube.com), which the backend's CORS
 *     policy rejects and which Private Network Access blocks from reaching
 *     127.0.0.1. Requests made here run with the extension's own origin and
 *     host permissions, so they succeed.
 *
 *  2. Track which downloads are running. Service workers are torn down after
 *     ~30s idle, so this lives in chrome.storage rather than a module variable
 *     — otherwise reopening the popup would lose a download still running in
 *     the backend. The backend stays the source of truth; this is only a hint
 *     about which task to resume watching.
 */

importScripts("/lib/api-client.js");

const KEY = "activeDownloads";

// Reads and writes are serialized through this chain. Without it, the popup
// registering a download and the worker's eviction pass can read the same
// snapshot and the later write silently drops the other's change.
let queue = Promise.resolve();

function exclusive(work) {
  const result = queue.then(work, work);
  queue = result.then(
    () => undefined,
    () => undefined
  );
  return result;
}

async function readActive() {
  const stored = await chrome.storage.local.get(KEY);
  return stored[KEY] || {};
}

async function writeActive(downloads) {
  await chrome.storage.local.set({ [KEY]: downloads });
  const count = Object.keys(downloads).length;
  await chrome.action.setBadgeText({ text: count ? String(count) : "" });
  if (count) await chrome.action.setBadgeBackgroundColor({ color: "#e53e3e" });
}

const mutate = (change) =>
  exclusive(async () => {
    const downloads = await readActive();
    const next = change(downloads);
    await writeActive(next);
    return next;
  });

async function handle(message) {
  switch (message.type) {
    case "API_REQUEST": {
      try {
        return { ok: true, data: await ApiClient.rawRequest(message.path, message.options) };
      } catch (e) {
        const plain = typeof e?.toPlain === "function" ? e.toPlain() : { message: String(e?.message || e) };
        return { ok: false, error: plain };
      }
    }

    case "GET_VIDEO_URL": {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const isWatch = tab?.url?.includes("youtube.com/watch");
      return { url: isWatch ? tab.url : null };
    }

    case "DOWNLOAD_STARTED":
      await mutate((downloads) => ({
        ...downloads,
        [message.taskId]: { taskId: message.taskId, title: message.title, startedAt: Date.now() },
      }));
      return { ok: true };

    case "DOWNLOAD_COMPLETED":
      await mutate((downloads) => {
        const next = { ...downloads };
        delete next[message.taskId];
        return next;
      });
      return { ok: true };

    case "GET_ACTIVE_DOWNLOADS": {
      // Drop entries older than the backend's own task retention, so a crashed
      // download cannot pin the badge or hand the popup a dead task id.
      const cutoff = Date.now() - 30 * 60 * 1000;
      const downloads = await mutate((current) =>
        Object.fromEntries(Object.entries(current).filter(([, entry]) => entry.startedAt >= cutoff))
      );
      return { downloads };
    }

    default:
      return {};
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handle(message).then(sendResponse, (e) => sendResponse({ ok: false, error: { message: String(e) } }));
  return true; // keep the message channel open for the async reply
});
