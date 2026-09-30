// Audit page — lists every site/reports/audit-*.json via the backend's GET /reports.

const listEl = document.getElementById("tl-audit-list");

(async function loadReports() {
  try {
    const res = await fetch(`${BACKEND_URL}/reports`);
    if (!res.ok) throw new Error(`Backend returned HTTP ${res.status}`);
    const { reports } = await res.json();

    if (!reports || reports.length === 0) {
      listEl.innerHTML = `<p class="tl-muted">No audit reports yet. Ask Claude Code to run the
        feed-auditor subagent to generate one.</p>`;
      return;
    }

    listEl.innerHTML = reports.map(renderReport).join("");
  } catch (err) {
    listEl.innerHTML = `
      <div class="tl-note">
        Couldn't load reports from the backend at <code>${BACKEND_URL}</code>. Make sure it's
        running — see <a href="install.html">Install</a>. (${escapeHtml(String(err.message || err))})
      </div>
    `;
  }
})();

function renderReport(report) {
  if (report.error) {
    return `<div class="tl-card"><h3>${escapeHtml(report.filename)}</h3>
      <p class="tl-muted">Couldn't parse this report: ${escapeHtml(report.error)}</p></div>`;
  }

  const data = report.data;
  const summary = data.summary || {};
  const rows = (data.results || []).map(renderResultRow).join("");

  return `
    <div class="tl-card" style="margin-bottom: 24px;">
      <h3>${escapeHtml(report.filename)}</h3>
      <p class="tl-muted">
        ${escapeHtml(data.feed || "")} · ${data.shorts_completed ?? "?"} of
        ${data.shorts_requested ?? "?"} Shorts completed · ${escapeHtml(data.audit_date || "")}
      </p>
      <div class="tl-btn-row" style="margin-top: 0;">
        <span class="tl-pill tl-pill--real">${summary.likely_real ?? 0} Likely Real</span>
        <span class="tl-pill tl-pill--ai">${summary.likely_ai_generated ?? 0} Likely AI-Generated</span>
        <span class="tl-pill tl-pill--unsure">${summary.unsure ?? 0} Unsure</span>
        ${summary.error ? `<span class="tl-pill" style="background:#6b7280;">${summary.error} error</span>` : ""}
      </div>
      <div style="overflow-x:auto; margin-top: 16px;">
        <table class="tl-table">
          <thead>
            <tr><th>Short</th><th>Verdict</th><th>Confidence</th><th>Reason</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderResultRow(result) {
  const link = `<a href="${escapeHtml(result.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(result.title || result.url)}</a>`;

  if (result.error) {
    return `<tr><td>${link}</td><td colspan="3" class="tl-muted">Error: ${escapeHtml(result.error)}</td></tr>`;
  }

  const pillClass = tlPillClassFor(result.verdict);
  return `
    <tr>
      <td>${link}</td>
      <td><span class="tl-pill ${pillClass}">${escapeHtml(result.verdict)}</span></td>
      <td>${tlFormatConfidence(result.confidence)}</td>
      <td>${escapeHtml(result.reason || "")}</td>
    </tr>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
