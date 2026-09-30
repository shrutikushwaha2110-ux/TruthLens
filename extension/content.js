/**
 * TruthLens content script — runs on youtube.com and instagram.com.
 * Watches for the active Short/Reel/video, captures a few real frames of it,
 * sends them to the local backend for analysis, and shows a badge with the verdict.
 *
 * captureFrames() and showBadge() are standalone, reusable functions (not tied to any
 * one site's DOM beyond the passed-in <video> element) — the only per-platform code is
 * getContentId()/getPlatformLabel()/isDisclosed()/getCaption() below. Instagram support
 * currently covers Reels (video) only; static image feed posts are a separate future
 * addition, since they need a different capture path (no <video> element to sample).
 * A Facebook content script would follow the same pattern.
 */

(() => {
  console.log("[TruthLens] content script loaded on", location.href);

  const FRAME_DELAYS_MS = [500, 1500, 3000]; // ~0.5s, ~1.5s, ~3s into playback
  const MIN_DATA_URL_LENGTH = 1000; // shorter than this almost certainly means a blank frame
  const BACKEND_PING_INTERVAL_MS = 15000;

  let extensionEnabled = true;
  let backendOnline = true;
  let currentContentId = null;
  let currentRunToken = 0; // bumped every time we start tracking new content, to cancel stale timers

  // ---------- storage / on-off switch ----------

  chrome.storage.local.get({ tl_enabled: true }, (items) => {
    extensionEnabled = items.tl_enabled;
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && "tl_enabled" in changes) {
      extensionEnabled = changes.tl_enabled.newValue;
      if (!extensionEnabled) removeAllBadges();
    }
  });

  // ---------- finding the active video ----------

  function getActiveVideo() {
    const videos = document.querySelectorAll("video");
    let best = null;
    let bestArea = 0;
    for (const video of videos) {
      const rect = video.getBoundingClientRect();
      const visibleWidth = Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0);
      const visibleHeight = Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0);
      if (visibleWidth <= 0 || visibleHeight <= 0) continue;
      const area = visibleWidth * visibleHeight;
      if (area > bestArea) {
        bestArea = area;
        best = video;
      }
    }
    return best;
  }

  function isInstagram() {
    return location.hostname === "www.instagram.com";
  }

  function getContentId() {
    const path = location.pathname;

    if (path.startsWith("/shorts/")) {
      return `shorts:${path.split("/")[2]}`;
    }
    if (path.startsWith("/watch")) {
      const v = new URLSearchParams(location.search).get("v");
      if (v) return `watch:${v}`;
    }
    if (isInstagram()) {
      // Instagram Reels permalinks use either /reel/<shortcode>/ or /reels/<shortcode>/.
      const match = path.match(/^\/(?:reel|reels)\/([^/]+)/);
      if (match) return `instagram-reel:${match[1]}`;
    }
    return null;
  }

  function getPlatformLabel() {
    if (isInstagram()) return "instagram-reel";
    return location.pathname.startsWith("/shorts/") ? "youtube-shorts" : "youtube-watch";
  }

  function isDisclosed() {
    const text = document.body.innerText || "";
    // YouTube's disclosure label for creator-disclosed AI content.
    if (text.includes("Altered or synthetic content")) return true;
    // Meta's disclosure label, verified live on a real post on 2026-09-30 (a button/div
    // reading exactly "AI content"). "AI info" kept as a fallback in case an older or
    // regional build of the UI uses different wording.
    if (isInstagram() && (text.includes("AI content") || text.includes("AI info"))) return true;
    return false;
  }

  function getCaption() {
    const titleEl = document.querySelector(
      "yt-shorts-video-title-view-model, h1.ytd-watch-metadata, #title h1"
    );
    if (titleEl && titleEl.textContent.trim()) return titleEl.textContent.trim();

    if (isInstagram()) {
      // Verified live on 2026-09-30 against a real logged-in session: Instagram's Reels
      // caption has NO <article> wrapper at all (unlike feed posts), and isn't a real
      // <button> — it's a div[role="button"] that also wraps the post's hashtag links
      // (e.g. <a href="/explore/tags/...">). Multiple Reels are preloaded in the DOM at
      // once, so anchor on a hashtag link that's actually visible in the viewport right
      // now, then walk up to its role="button" wrapper. A caption with no hashtags at
      // all isn't found this way and falls back to document.title below — an accepted
      // limitation, not every caption uses hashtags.
      const tagLinks = Array.from(document.querySelectorAll('a[href*="/explore/tags/"]'));
      const visibleLink = tagLinks.find((a) => {
        const r = a.getBoundingClientRect();
        return (
          r.width > 0 &&
          r.height > 0 &&
          r.top < window.innerHeight &&
          r.bottom > 0 &&
          r.left < window.innerWidth &&
          r.right > 0
        );
      });
      if (visibleLink) {
        let el = visibleLink;
        for (let i = 0; i < 4 && el.parentElement; i++) {
          el = el.parentElement;
          if (el.getAttribute("role") === "button") break;
        }
        if (el.textContent && el.textContent.trim()) return el.textContent.trim();
      }
    }

    return document.title || null;
  }

  // ---------- frame capture (reusable) ----------

  /**
   * Captures one frame of `element` (a <video>) as a base64 JPEG data URL.
   * Method A: draw the video onto a canvas directly (fast, no extra permissions).
   * Method B (fallback): ask the background worker to screenshot the visible tab,
   * then crop to the element's on-screen rect. Used when Method A throws
   * (e.g. SecurityError on a tainted canvas) or produces a suspiciously tiny image.
   */
  async function captureFrames(element) {
    const viaCanvas = tryCanvasCapture(element);
    if (viaCanvas && viaCanvas.length >= MIN_DATA_URL_LENGTH) {
      console.log(`[TruthLens] frame captured via canvas (${viaCanvas.length} bytes)`);
      return viaCanvas;
    }
    console.log("[TruthLens] canvas capture failed/too small, falling back to tab capture");
    const viaTab = await tryTabCapture(element);
    console.log(`[TruthLens] frame captured via tab capture: ${viaTab ? viaTab.length + " bytes" : "FAILED"}`);
    return viaTab;
  }

  function tryCanvasCapture(videoElement) {
    try {
      const maxWidth = 512;
      const scale = Math.min(1, maxWidth / videoElement.videoWidth);
      const width = Math.max(1, Math.round(videoElement.videoWidth * scale));
      const height = Math.max(1, Math.round(videoElement.videoHeight * scale));

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(videoElement, 0, 0, width, height);
      // Higher JPEG quality reduces compression artifacts that can confuse the
      // AI detectors into misreading real footage (they key on subtle high-frequency
      // noise patterns that heavy compression distorts).
      return canvas.toDataURL("image/jpeg", 0.95);
    } catch (err) {
      // SecurityError (tainted canvas) or similar — fall back to tab capture.
      return null;
    }
  }

  async function tryTabCapture(videoElement) {
    hideAllBadges();
    try {
      const response = await sendMessage({ type: "CAPTURE_TAB" });
      if (!response || !response.ok) return null;

      const rect = videoElement.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      return await cropDataUrl(response.dataUrl, {
        x: rect.left * dpr,
        y: rect.top * dpr,
        width: rect.width * dpr,
        height: rect.height * dpr,
      });
    } finally {
      showAllBadges();
    }
  }

  function cropDataUrl(dataUrl, cropRect) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(cropRect.width));
        canvas.height = Math.max(1, Math.round(cropRect.height));
        const ctx = canvas.getContext("2d");
        ctx.drawImage(
          img,
          cropRect.x,
          cropRect.y,
          cropRect.width,
          cropRect.height,
          0,
          0,
          canvas.width,
          canvas.height
        );
        resolve(canvas.toDataURL("image/jpeg", 0.95));
      };
      img.onerror = reject;
      img.src = dataUrl;
    });
  }

  function sendMessage(message) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(response);
        }
      });
    });
  }

  // ---------- badge UI (reusable) ----------

  // YouTube's player DOM has several nested stacking contexts (controls, overlays,
  // engagement panels) with their own high z-index values. A badge nested inside the
  // video's own container can never render above those sibling subtrees, no matter how
  // high its z-index is set, because it's trapped inside its parent's stacking context.
  // So instead we attach a single badge directly to <body> with `position: fixed` and
  // continuously reposition it over the active video's on-screen rect — the same
  // technique used by most "overlay on video" browser extensions.
  let activeBadgeEl = null;
  let activeBadgeVideo = null;

  function ensureBadgeElement() {
    if (activeBadgeEl) return activeBadgeEl;
    activeBadgeEl = document.createElement("div");
    activeBadgeEl.className = "tl-badge";
    const popover = document.createElement("div");
    popover.className = "tl-popover tl-hidden";
    activeBadgeEl.appendChild(popover);
    activeBadgeEl.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      popover.classList.toggle("tl-hidden");
    });
    document.body.appendChild(activeBadgeEl);
    return activeBadgeEl;
  }

  function positionBadge(videoEl) {
    if (!activeBadgeEl || !videoEl) return;
    const rect = videoEl.getBoundingClientRect();
    activeBadgeEl.style.top = `${Math.round(rect.top + 12)}px`;
    activeBadgeEl.style.left = `${Math.round(rect.left + 12)}px`;
  }

  function showBadge(element, state) {
    activeBadgeVideo = element;
    const badge = ensureBadgeElement();
    positionBadge(element);
    renderBadgeState(badge, state);
  }

  function renderBadgeState(badge, state) {
    badge.classList.remove(
      "tl-checking",
      "tl-real",
      "tl-ai",
      "tl-unsure",
      "tl-disclosed",
      "tl-error"
    );

    const popover = badge.querySelector(".tl-popover");
    const wasHidden = popover.classList.contains("tl-hidden");

    if (state.status === "checking") {
      badge.classList.add("tl-checking");
      badge.textContent = "Checking…";
      badge.appendChild(popover);
      popover.innerHTML = "";
      return;
    }

    if (state.status === "error") {
      badge.classList.add("tl-error");
      badge.textContent = "TruthLens: error";
      badge.appendChild(popover);
      popover.innerHTML = `<p>${escapeHtml(state.message || "Something went wrong.")}</p>`;
      return;
    }

    const result = state.result;
    const labelClass =
      {
        "Likely Real": "tl-real",
        "Likely AI-Generated": "tl-ai",
        Unsure: "tl-unsure",
        "AI-Generated (creator disclosed)": "tl-disclosed",
      }[result.verdict] || "tl-unsure";

    badge.classList.add(labelClass);
    const confidenceText = result.confidence != null ? ` · ${result.confidence}%` : "";
    badge.textContent = `${result.verdict}${confidenceText}`;

    if (result.factcheck) {
      const flag = document.createElement("span");
      flag.className = "tl-flag";
      flag.textContent = ` ⚠ ${result.factcheck.label}`;
      badge.appendChild(flag);
    }

    badge.appendChild(popover);
    popover.innerHTML = renderPopoverContent(result);
    popover.classList.toggle("tl-hidden", wasHidden);
  }

  function renderPopoverContent(result) {
    const reasons = (result.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("");
    const frames = (result.frames || [])
      .map(
        (f, i) =>
          `<li>Frame ${i + 1}: ateeqq ${(f.ateeqq * 100).toFixed(0)}%, sdxl-detector ${(
            f.sdxl_detector * 100
          ).toFixed(0)}% AI</li>`
      )
      .join("");
    const factcheckLink = result.factcheck && result.factcheck.url
      ? `<p><a href="${escapeHtml(result.factcheck.url)}" target="_blank" rel="noopener noreferrer">Fact-check source</a></p>`
      : "";

    return `
      <ul class="tl-reasons">${reasons}</ul>
      <ul class="tl-frames">${frames}</ul>
      ${factcheckLink}
    `;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function removeAllBadges() {
    if (activeBadgeEl) {
      activeBadgeEl.remove();
      activeBadgeEl = null;
      activeBadgeVideo = null;
    }
  }

  function hideAllBadges() {
    if (activeBadgeEl) activeBadgeEl.style.visibility = "hidden";
  }

  function showAllBadges() {
    if (activeBadgeEl) activeBadgeEl.style.visibility = "";
  }

  // ---------- backend health banner ----------

  let banner = null;

  function showOfflineBanner() {
    if (banner) return;
    banner = document.createElement("div");
    banner.className = "tl-offline-banner";
    banner.textContent = "TruthLens backend offline";
    document.body.appendChild(banner);
  }

  function hideOfflineBanner() {
    if (banner) {
      banner.remove();
      banner = null;
    }
  }

  async function checkBackendHealth() {
    const response = await sendMessage({ type: "PING_BACKEND" });
    backendOnline = !!(response && response.ok);
    if (backendOnline) hideOfflineBanner();
    else showOfflineBanner();
  }

  setInterval(checkBackendHealth, BACKEND_PING_INTERVAL_MS);
  checkBackendHealth();

  // ---------- main analysis pipeline ----------

  async function analyzeNewContent(video, contentId, runToken) {
    const t0 = performance.now();
    showBadge(video, { status: "checking" });

    const frames = [];
    let elapsed = 0;
    for (const delay of FRAME_DELAYS_MS) {
      await sleep(delay - elapsed);
      elapsed = delay;
      if (runToken !== currentRunToken) return; // a newer Short started; abandon this one
      const frame = await captureFrames(video);
      if (frame) frames.push(frame);
    }

    if (runToken !== currentRunToken) return;
    const tCaptureDone = performance.now();

    if (frames.length === 0) {
      showBadge(video, { status: "error", message: "Could not capture any video frames." });
      return;
    }

    const payload = {
      id: contentId,
      platform: getPlatformLabel(),
      frames,
      disclosed: isDisclosed(),
      caption: getCaption(),
    };

    const response = await sendMessage({ type: "ANALYZE_FRAMES", payload });
    const tBackendDone = performance.now();
    if (runToken !== currentRunToken) return;

    if (!response || !response.ok) {
      backendOnline = false;
      showOfflineBanner();
      showBadge(video, { status: "error", message: "TruthLens backend offline" });
      return;
    }

    backendOnline = true;
    hideOfflineBanner();
    showBadge(video, { status: "done", result: response.data });

    const frameScores = (response.data.frames || [])
      .map(
        (f, i) =>
          `frame${i + 1}(ateeqq=${(f.ateeqq * 100).toFixed(0)}% sdxl=${(f.sdxl_detector * 100).toFixed(0)}%)`
      )
      .join(" ");

    console.log(
      `[TruthLens] ${contentId}: verdict=${response.data.verdict}` +
        (response.data.confidence != null ? ` (${response.data.confidence}%)` : "") +
        ` | capture=${(tCaptureDone - t0).toFixed(0)}ms` +
        ` backend=${(tBackendDone - tCaptureDone).toFixed(0)}ms` +
        ` total=${(tBackendDone - t0).toFixed(0)}ms` +
        ` | ${frameScores}` +
        ` | reasons: ${(response.data.reasons || []).join(" / ")}`
    );
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
  }

  // ---------- detection loop ----------

  let lastNoVideoLog = 0;

  function tick() {
    if (!extensionEnabled) return;

    const video = getActiveVideo();
    const contentId = getContentId();

    // Keep the badge glued to the active video's on-screen position even between
    // content changes (YouTube's Shorts shelf reflows as the user scrolls).
    if (video && video === activeBadgeVideo) {
      positionBadge(video);
    }

    if (!video || !contentId) {
      const now = Date.now();
      if (now - lastNoVideoLog > 5000) {
        console.log("[TruthLens] tick: video=", !!video, "contentId=", contentId);
        lastNoVideoLog = now;
      }
      return;
    }

    if (contentId !== currentContentId) {
      console.log("[TruthLens] new content detected:", contentId);
      currentContentId = contentId;
      currentRunToken += 1;
      analyzeNewContent(video, contentId, currentRunToken).catch((err) =>
        console.error("[TruthLens] analyzeNewContent failed:", err)
      );
    }
  }

  setInterval(tick, 500);
  document.addEventListener("yt-navigate-finish", tick);
  window.addEventListener("popstate", tick);
})();
