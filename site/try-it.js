// Try It page — uploads an image to the local backend's /analyze/image endpoint
// and renders the returned verdict as a card.

const form = document.getElementById("tl-try-form");
const fileInput = document.getElementById("tl-file-input");
const resultEl = document.getElementById("tl-result");
const analyzeBtn = document.getElementById("tl-analyze-btn");
const previewWrap = document.getElementById("tl-preview-wrap");
const previewImg = document.getElementById("tl-preview-img");

let previewObjectUrl = null;

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) {
    previewWrap.hidden = true;
    return;
  }

  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = URL.createObjectURL(file);
  previewImg.src = previewObjectUrl;
  previewImg.alt = `Preview of the selected file: ${file.name}`;
  previewWrap.hidden = false;
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyzing…";
  resultEl.innerHTML = `<p class="tl-muted">Running both detectors on your image…</p>`;

  try {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${BACKEND_URL}/analyze/image`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) throw new Error(`Backend returned HTTP ${res.status}`);
    const data = await res.json();
    renderResult(data);
  } catch (err) {
    resultEl.innerHTML = `
      <div class="tl-note">
        Couldn't reach the TruthLens backend. Make sure it's running at
        <code>${BACKEND_URL}</code> — see <a href="install.html">Install</a> for the exact
        command. (${escapeHtml(String(err.message || err))})
      </div>
    `;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Analyze";
  }
});

function renderResult(data) {
  const pillClass = tlPillClassFor(data.verdict);
  const confidenceText = tlFormatConfidence(data.confidence);

  const reasons = (data.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("");

  const frame = (data.frames || [])[0];
  const frameScores = frame
    ? `<p class="tl-muted">ateeqq: ${(frame.ateeqq * 100).toFixed(0)}% AI ·
       sdxl-detector: ${(frame.sdxl_detector * 100).toFixed(0)}% AI</p>`
    : "";

  const factcheck = data.factcheck
    ? `<p><span class="tl-pill tl-pill--ai">${escapeHtml(data.factcheck.label)}</span>
       ${data.factcheck.url ? ` — <a href="${escapeHtml(data.factcheck.url)}" target="_blank" rel="noopener noreferrer">source</a>` : ""}</p>`
    : "";

  resultEl.innerHTML = `
    <div class="tl-card" style="margin-top: 20px;">
      <span class="tl-pill ${pillClass}">${escapeHtml(data.verdict)} · ${confidenceText}</span>
      <ul style="margin-top: 14px;">${reasons}</ul>
      ${frameScores}
      ${factcheck}
    </div>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
