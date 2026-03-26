/**
 * MV3 Service Worker — manages download state across popup open/close cycles.
 */

// Store active downloads so the popup can recover state
let activeDownloads = {};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "GET_VIDEO_URL":
      // Get the URL from the active YouTube tab
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const tab = tabs[0];
        if (tab && tab.url && tab.url.includes("youtube.com/watch")) {
          sendResponse({ url: tab.url });
        } else {
          sendResponse({ url: null });
        }
      });
      return true; // async response

    case "DOWNLOAD_STARTED":
      // Store download info for persistence across popup reopens
      activeDownloads[message.taskId] = {
        taskId: message.taskId,
        title: message.title,
        startedAt: Date.now(),
      };
      // Update badge to show active downloads
      updateBadge();
      sendResponse({ ok: true });
      return false;

    case "DOWNLOAD_COMPLETED":
      delete activeDownloads[message.taskId];
      updateBadge();
      sendResponse({ ok: true });
      return false;

    case "GET_ACTIVE_DOWNLOADS":
      sendResponse({ downloads: activeDownloads });
      return false;

    default:
      return false;
  }
});

function updateBadge() {
  const count = Object.keys(activeDownloads).length;
  if (count > 0) {
    chrome.action.setBadgeText({ text: String(count) });
    chrome.action.setBadgeBackgroundColor({ color: "#e53e3e" });
  } else {
    chrome.action.setBadgeText({ text: "" });
  }
}
