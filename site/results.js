// Results page — reads site/data/eval.json, written by scripts/evaluate.py.
// That file doesn't exist until the Step 6 evaluation has been run at least once.

const resultsEl = document.getElementById("tl-results");

(async function loadEval() {
  try {
    const res = await fetch("data/eval.json", { cache: "no-store" });
    if (res.status === 404) {
      resultsEl.innerHTML = `
        <div class="tl-note">
          No evaluation has been run yet. Add labeled images to <code>eval/real/</code> and
          <code>eval/ai/</code>, then run <code>scripts/evaluate.py</code> to generate this page's
          data.
        </div>
      `;
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    render(data);
  } catch (err) {
    resultsEl.innerHTML = `
      <div class="tl-note">
        Couldn't load evaluation data. (${escapeHtml(String(err.message || err))})
      </div>
    `;
  }
})();

function render(data) {
  const overallPct = data.overall_accuracy != null ? `${(data.overall_accuracy * 100).toFixed(0)}%` : "—";
  const decisivePct = data.decisive_accuracy != null ? `${(data.decisive_accuracy * 100).toFixed(0)}%` : "—";
  const perModel = data.per_model_accuracy || {};
  const counts = data.counts || {};

  const perModelRows = Object.entries(perModel)
    .map(([model, acc]) => `<tr><td>${escapeHtml(model)}</td><td>${(acc * 100).toFixed(0)}%</td></tr>`)
    .join("");

  const countRows = Object.entries(counts)
    .map(
      ([folder, c]) => `
        <tr>
          <td>${escapeHtml(folder)}</td>
          <td>${c.total ?? "—"}</td>
          <td>${c.likely_real ?? 0}</td>
          <td>${c.likely_ai_generated ?? 0}</td>
          <td>${c.unsure ?? 0}</td>
        </tr>
      `
    )
    .join("");

  resultsEl.innerHTML = `
    <div class="tl-grid" style="margin-bottom: 24px;">
      <div class="tl-card">
        <h3>Total images</h3>
        <p style="font-size: 28px; font-weight: 800; color: var(--color-text);">${data.total_images ?? "—"}</p>
      </div>
      <div class="tl-card">
        <h3>Overall accuracy</h3>
        <p style="font-size: 28px; font-weight: 800; color: var(--color-text);">${overallPct}</p>
        <p class="tl-muted">Counts "Unsure" as not-correct — it didn't give the right answer.</p>
      </div>
      <div class="tl-card">
        <h3>Accuracy when decisive</h3>
        <p style="font-size: 28px; font-weight: 800; color: var(--color-text);">${decisivePct}</p>
        <p class="tl-muted">
          Only counts the ${data.decisive_count ?? "—"} image(s) where TruthLens actually
          committed to Likely Real/AI-Generated (excludes the ${data.unsure_count ?? "—"} it
          called "Unsure"). This shows whether misses above are honest abstentions or actual
          wrong answers.
        </p>
      </div>
    </div>

    <h2>Per-model accuracy</h2>
    <table class="tl-table" style="margin-bottom: 24px;">
      <thead><tr><th>Model</th><th>Accuracy</th></tr></thead>
      <tbody>${perModelRows || `<tr><td colspan="2" class="tl-muted">No data</td></tr>`}</tbody>
    </table>

    <h2>Real vs. AI breakdown</h2>
    <table class="tl-table">
      <thead><tr><th>Folder</th><th>Total</th><th>Likely Real</th><th>Likely AI-Generated</th><th>Unsure</th></tr></thead>
      <tbody>${countRows || `<tr><td colspan="5" class="tl-muted">No data</td></tr>`}</tbody>
    </table>

    <p class="tl-muted" style="margin-top:16px;">Generated ${escapeHtml(data.generated_at || "")}.
       Small test set — treat these numbers as a snapshot, not a guarantee.</p>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
