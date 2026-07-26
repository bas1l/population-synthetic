"use strict";

// Top-level view tabs: "Generation DAG" (the existing explorer) and
// "By output category" (the candidate-table catalog, built lazily on first open).
(function () {
  const tabs = Array.from(document.querySelectorAll(".viewtabs .viewtab"));
  const views = {
    stats: document.getElementById("view-stats"),
    dag: document.getElementById("view-dag"),
    catalog: document.getElementById("view-catalog"),
  };

  function show(view) {
    tabs.forEach(t => {
      const on = t.dataset.view === view;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
    });
    Object.keys(views).forEach(k => { if (views[k]) views[k].hidden = (k !== view); });
    if (view === "catalog" && typeof window.buildCatalog === "function") window.buildCatalog();
    if (view === "stats" && typeof window.buildStats === "function") window.buildStats();
  }

  tabs.forEach((t, i) => {
    t.addEventListener("click", () => show(t.dataset.view));
    t.addEventListener("keydown", ev => {
      let j = null;
      if (ev.key === "ArrowRight" || ev.key === "ArrowDown") j = (i + 1) % tabs.length;
      else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") j = (i - 1 + tabs.length) % tabs.length;
      if (j == null) return;
      ev.preventDefault();
      tabs[j].focus();
      show(tabs[j].dataset.view);
    });
  });
})();
