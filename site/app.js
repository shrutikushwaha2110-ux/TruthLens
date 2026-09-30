// TruthLens site — shared helpers used across pages.

const BACKEND_URL = window.location.origin;

// Highlight the current page's nav link.
(function highlightNav() {
  const path = window.location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll(".tl-nav-links a").forEach((link) => {
    const href = link.getAttribute("href");
    if (href === path) {
      link.setAttribute("aria-current", "page");
    }
  });
})();

// Turns a verdict object (from /analyze/image or /analyze/frames) into the same
// pill classes/colors the Chrome extension uses, for visual consistency.
function tlPillClassFor(verdict) {
  return (
    {
      "Likely Real": "tl-pill--real",
      "Likely AI-Generated": "tl-pill--ai",
      Unsure: "tl-pill--unsure",
      "AI-Generated (creator disclosed)": "tl-pill--disclosed",
    }[verdict] || "tl-pill--unsure"
  );
}

function tlFormatConfidence(confidence) {
  return confidence != null ? `${confidence}%` : "—";
}
