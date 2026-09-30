/**
 * TruthLens background service worker.
 * Content scripts can't call localhost directly (blocked by page CSP / not their job),
 * so all backend requests and tab-capture calls are routed through here.
 */

const BACKEND_URL = "http://localhost:8000";

// chrome.tabs.captureVisibleTab is rate-limited by Chrome to ~2/sec per window.
// We enforce a minimum spacing ourselves so we don't get silently throttled/errored.
const MIN_CAPTURE_INTERVAL_MS = 550;
let lastCaptureTime = 0;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "ANALYZE_FRAMES") {
    fetch(`${BACKEND_URL}/analyze/frames`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.payload),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true; // keep the message channel open for the async response
  }

  if (message.type === "CAPTURE_TAB") {
    const windowId = sender.tab ? sender.tab.windowId : undefined;
    const runCapture = () => {
      lastCaptureTime = Date.now();
      chrome.tabs.captureVisibleTab(windowId, { format: "jpeg", quality: 70 }, (dataUrl) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ ok: true, dataUrl });
        }
      });
    };
    const elapsed = Date.now() - lastCaptureTime;
    const wait = Math.max(0, MIN_CAPTURE_INTERVAL_MS - elapsed);
    setTimeout(runCapture, wait);
    return true;
  }

  if (message.type === "PING_BACKEND") {
    fetch(`${BACKEND_URL}/docs`)
      .then((res) => sendResponse({ ok: res.ok }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  return false;
});
