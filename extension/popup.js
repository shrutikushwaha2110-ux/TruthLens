const toggle = document.getElementById("tl-enabled-toggle");

chrome.storage.local.get({ tl_enabled: true }, (items) => {
  toggle.checked = items.tl_enabled;
});

toggle.addEventListener("change", () => {
  chrome.storage.local.set({ tl_enabled: toggle.checked });
});
