/**
 * Content script — injected into YouTube watch pages.
 *
 * Responsibilities:
 * - Detect YouTube video pages
 * - Provide video URL to popup/service worker
 * - NO YouTube internal parsing (all extraction delegated to backend)
 */

(() => {
  // Listen for URL requests from popup or service worker
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "GET_PAGE_URL") {
      sendResponse({ url: window.location.href });
      return false;
    }
  });
})();
