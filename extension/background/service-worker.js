/**
 * MV3 service worker.
 *
 * Service workers are torn down after ~30 seconds of inactivity, so the set of
 * running downloads lives in chrome.storage rather than a module variable —
 * otherwise reopening the popup would lose track of a download still running
 * in the backend. The backend remains the source of truth; this is only a hint
 * about which task to resume watching.
 */

const KEY = "activeDownloads";

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

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    switch (message.type) {
      case "GET_VIDEO_URL": {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const isWatch = tab?.url?.includes("youtube.com/watch");
        sendResponse({ url: isWatch ? tab.url : null });
        break;
      }

      case "DOWNLOAD_STARTED": {
        const downloads = await readActive();
        downloads[message.taskId] = { taskId: message.taskId, title: message.title, startedAt: Date.now() };
        await writeActive(downloads);
        sendResponse({ ok: true });
        break;
      }

      case "DOWNLOAD_COMPLETED": {
        const downloads = await readActive();
        delete downloads[message.taskId];
        await writeActive(downloads);
        sendResponse({ ok: true });
        break;
      }

      case "GET_ACTIVE_DOWNLOADS": {
        const downloads = await readActive();
        // Drop anything old enough that its task has certainly been evicted
        // server-side, so a crashed download cannot pin the badge forever.
        const cutoff = Date.now() - 2 * 3600 * 1000;
        let changed = false;
        for (const [id, entry] of Object.entries(downloads)) {
          if (entry.startedAt < cutoff) {
            delete downloads[id];
            changed = true;
          }
        }
        if (changed) await writeActive(downloads);
        sendResponse({ downloads });
        break;
      }

      default:
        sendResponse({});
    }
  })();

  return true; // keep the message channel open for the async reply
});
