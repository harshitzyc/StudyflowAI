/* StudyFlow dashboard — live API rendering, interruption-safe controls.
   Rule: the newest click always wins. A new request aborts the stale one,
   so no button is ever silently ignored. All API text uses textContent. */
(function () {
    // Check if data was injected by Streamlit parent
  if (window.STUDYFLOW_DATA) {
    const mockFetch = (url) => {
        if (url.includes('/weightages')) return Promise.resolve({ ok: true, json: () => Promise.resolve(window.STUDYFLOW_DATA.weightages) });
        if (url.includes('/frequencies')) return Promise.resolve({ ok: true, json: () => Promise.resolve(window.STUDYFLOW_DATA.frequencies) });
        if (url.includes('/plan')) return Promise.resolve({ ok: true, json: () => Promise.resolve(window.STUDYFLOW_DATA.plan) });
        return Promise.reject(new Error('Unknown endpoint'));
    };
    
    // Override global fetch for these endpoints only
    const originalFetch = window.fetch;
    window.fetch = (url, opts) => {
        if (typeof url === 'string' && (url.includes('/weightages') || url.includes('/frequencies') || url.includes('/plan'))) {
            return mockFetch(url);
        }
        return originalFetch(url, opts);
    };
}
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const state = {
    committedHours: 20,
    ctrl: { plan: null, weightages: null, frequencies: null, export: null },
    exportBusy: false,
  };

  /* ── helpers ─────────────────────────────────────────────────── */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function toast(message, tone = "info", ms = 6000) {
    let host = $("#sf-toasts");
    if (!host) {
      host = el("div", "sf-toast-host");
      host.id = "sf-toasts";
      host.setAttribute("role", "status");
      host.setAttribute("aria-live", "polite");
      document.body.appendChild(host);
    }
    const icons = {
      success: "bi-check-circle-fill", danger: "bi-x-circle-fill",
      warning: "bi-exclamation-triangle-fill", info: "bi-info-circle-fill",
    };
    const box = el("div", "sf-toast sf-toast-" + tone);
    const close = el("button", "sf-toast-close");
    close.type = "button";
    close.setAttribute("aria-label", "Dismiss notification");
    close.appendChild(el("i", "bi bi-x-lg"));
    box.append(el("i", "bi " + (icons[tone] || icons.info)), el("div", "sf-toast-text", message), close);
    host.appendChild(box);
    requestAnimationFrame(() => box.classList.add("shown"));

    let timer = setTimeout(dismiss, ms);
    function dismiss() {
      clearTimeout(timer);
      box.classList.remove("shown");
      setTimeout(() => box.remove(), 350);
    }
    close.addEventListener("click", dismiss);
  }

  // Abort whatever this panel was doing; the caller becomes the current request.
  function beginRequest(key) {
    const old = state.ctrl[key];
    if (old) { old._superseded = true; old.abort(); }
    const ctrl = new AbortController();
    state.ctrl[key] = ctrl;
    return ctrl;
  }
  const isCurrent = (key, ctrl) => state.ctrl[key] === ctrl;

  async function getJSON(url, ctrl, timeoutMs = 120000) {
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: ctrl.signal, headers: { Accept: "application/json" } });
      if (!res.ok) {
        let detail = "Request failed (HTTP " + res.status + ").";
        try {
          const body = await res.json();
          if (body && body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } catch (_) { /* non-JSON error body */ }
        throw new Error(detail);
      }
      const data = await res.json();
      if (!data || typeof data !== "object") throw new Error("The API returned an unexpected response.");
      return data;
    } catch (err) {
      if (err.name === "AbortError") {
        if (ctrl._superseded) { const e = new Error("superseded"); e.superseded = true; throw e; }
        throw new Error("Timed out — the AI analysis is taking too long. Please retry.");
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  function setState(panelId, s) {
    const panel = $("#" + panelId);
    panel.querySelector("[data-loading]").hidden = s !== "loading";
    panel.querySelector("[data-error]").hidden = s !== "error";
    panel.querySelector("[data-content]").hidden = s !== "ready";
  }

  function showError(panelId, err) {
    $("#" + panelId).querySelector("[data-error-text]").textContent = err.message || String(err);
    setState(panelId, "error");
  }

  function emptyNote(container, text) {
    const box = el("div", "sf-empty-note");
    box.append(el("i", "bi bi-inbox"), el("span", null, text));
    container.replaceChildren(box);
  }

  function progressBar(pct, tone) {
    const wrap = el("div", "progress sf-progress");
    const bar = el("div", "progress-bar " + tone);
    bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
    wrap.appendChild(bar);
    return wrap;
  }

  const sortedEntries = (obj) => Object.entries(obj).sort((a, b) => b[1] - a[1]);

  /* ── unit weightages ─────────────────────────────────────────── */
  async function loadWeightages() {
    const ctrl = beginRequest("weightages");
    setState("panel-weightages", "loading");
    try {
      const data = await getJSON("/weightages", ctrl);
      if (!isCurrent("weightages", ctrl)) return;
      const entries = sortedEntries(data);
      const body = $("#weightage-body");
      body.replaceChildren();
      if (!entries.length) {
        emptyNote(body, "No unit weightage yet — Gemini couldn't map questions to units. Check the PDFs and retry.");
        $("#sum-units").textContent = "0";
      } else {
        const total = entries.reduce((s, [, n]) => s + n, 0);
        entries.forEach(([unit, count]) => {
          const pct = total ? (count / total) * 100 : 0;
          const row = el("div", "sf-unit-row");
          const head = el("div", "d-flex justify-content-between align-items-baseline gap-2 mb-1");
          head.append(
            el("span", "fw-semibold text-truncate", unit),
            el("span", "small text-secondary sf-num", count + " questions · " + pct.toFixed(1) + "%")
          );
          row.append(head, progressBar(pct, "bg-info"));
          body.appendChild(row);
        });
        $("#sum-units").textContent = entries.length;
      }
      setState("panel-weightages", "ready");
    } catch (err) {
      if (err.superseded || !isCurrent("weightages", ctrl)) return;
      showError("panel-weightages", err);
    }
  }

  /* ── PYQ topic frequencies ───────────────────────────────────── */
  async function loadFrequencies() {
    const ctrl = beginRequest("frequencies");
    setState("panel-frequencies", "loading");
    try {
      const data = await getJSON("/frequencies", ctrl);
      if (!isCurrent("frequencies", ctrl)) return;
      const entries = sortedEntries(data);
      const body = $("#freq-body");
      body.replaceChildren();
      if (!entries.length) {
        emptyNote(body, "No questions could be mapped to topics. Usually the PDFs have no extractable text, or the mapping failed — check them and retry.");
        $("#sum-topics").textContent = "0";
        $("#sum-questions").textContent = "0";
      } else {
        const max = entries[0][1];
        entries.forEach(([topic, count], i) => {
          const row = el("div", "sf-freq-row d-flex align-items-center gap-3" + (i === 0 ? " sf-top" : ""));
          row.appendChild(el("span", "sf-rank font-display", String(i + 1)));
          const main = el("div", "flex-grow-1 min-w-0");
          const head = el("div", "d-flex justify-content-between align-items-center gap-2 mb-1");
          head.append(el("span", "fw-semibold text-truncate", topic), el("span", "badge sf-chip-count", "×" + count));
          const thin = progressBar(max ? (count / max) * 100 : 0, "bg-warning");
          thin.classList.add("sf-progress-thin");
          main.append(head, thin);
          row.appendChild(main);
          body.appendChild(row);
        });
        $("#sum-topics").textContent = entries.length;
        $("#sum-questions").textContent = entries.reduce((s, [, n]) => s + n, 0);
      }
      setState("panel-frequencies", "ready");
    } catch (err) {
      if (err.superseded || !isCurrent("frequencies", ctrl)) return;
      showError("panel-frequencies", err);
    }
  }

  /* ── study plan ──────────────────────────────────────────────── */
  function setPlanBusy(busy) {
    $("#plan-spinner").classList.toggle("d-none", !busy);
    $("#plan-btn-icon").classList.toggle("d-none", busy);
    $("#plan-btn-label").textContent = busy ? "Updating…" : "Rebuild plan";
    // Button stays clickable on purpose: clicking again restarts with the newest hours.
  }

  function markSelectedPreset(hours) {
    $$("[data-hours]").forEach((b) => {
      const on = Number(b.getAttribute("data-hours")) === hours;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }

  async function loadPlan(hours) {
    const ctrl = beginRequest("plan");
    setPlanBusy(true);
    setState("panel-plan", "loading");
    try {
      const data = await getJSON("/plan?hours=" + hours, ctrl);
      if (!isCurrent("plan", ctrl)) return;
      const body = $("#plan-body");
      body.replaceChildren();

      if (typeof data.message === "string") {
        emptyNote(body, data.message);
        $("#sum-hours").textContent = "—";
      } else {
        const entries = Object.entries(data).sort((a, b) => b[1].recommended_hours - a[1].recommended_hours);
        if (!entries.length) {
          emptyNote(body, "The planner returned an empty plan. Check the PDFs and retry.");
          $("#sum-hours").textContent = "—";
        } else {
          const stamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
          const caption = el("div", "sf-plan-caption small text-secondary mb-2");
          caption.append(
            el("span", "badge sf-chip-count", hours + " h"),
            el("span", null, "allocated by exam weightage · updated " + stamp)
          );
          body.appendChild(caption);

          let sumQ = 0, sumW = 0, sumH = 0;
          const table = el("table", "table sf-plan-table align-middle mb-0");
          const hr = el("tr");
          ["Unit", "PYQs", "Weightage", "Recommended"].forEach((h) => hr.appendChild(el("th", null, h)));
          table.appendChild(el("thead")).appendChild(hr);

          const tbody = el("tbody");
          entries.forEach(([unit, d]) => {
            sumQ += d.questions_appeared; sumW += d.weightage_percentage; sumH += d.recommended_hours;
            const tr = el("tr");
            tr.appendChild(el("td", "fw-semibold", unit));
            tr.appendChild(el("td", "sf-num", String(d.questions_appeared)));
            tr.appendChild(el("td", "sf-num", d.weightage_percentage + "%"));
            const tdH = el("td");
            tdH.appendChild(el("span", "sf-hours-chip", d.recommended_hours + " h"));
            tr.appendChild(tdH);
            tbody.appendChild(tr);
          });
          table.appendChild(tbody);

          const fr = el("tr");
          fr.append(el("td", null, "Total"), el("td", "sf-num", String(sumQ)),
                    el("td", "sf-num", sumW.toFixed(1) + "%"), el("td", "sf-num", sumH.toFixed(1) + " h"));
          table.appendChild(el("tfoot")).appendChild(fr);

          const responsive = el("div", "table-responsive");
          responsive.appendChild(table);
          body.appendChild(responsive);
          $("#sum-hours").textContent = sumH.toFixed(1);
        }
      }

      state.committedHours = hours;
      markSelectedPreset(hours);
      syncExportHref();
      try { history.replaceState(null, "", "?hours=" + hours); } catch (_) { /* non-http context */ }
      setState("panel-plan", "ready");
    } catch (err) {
      if (err.superseded || !isCurrent("plan", ctrl)) return;
      showError("panel-plan", err);
    } finally {
      if (isCurrent("plan", ctrl)) setPlanBusy(false);
    }
  }

  /* ── PDF export: in-page download with real feedback ─────────── */
  function setExportBusy(busy) {
    state.exportBusy = busy;
    const link = $("#export-link");
    link.classList.toggle("disabled", busy);
    link.setAttribute("aria-disabled", String(busy));
    link.replaceChildren();
    if (busy) {
      link.append(el("span", "spinner-border spinner-border-sm me-1"), document.createTextNode("Generating…"));
    } else {
      link.append(el("i", "bi bi-file-earmark-pdf me-1"), document.createTextNode("Export PDF"));
    }
  }

  function syncExportHref() {
    const h = readHours();
    $("#export-link").href = "/export-pdf?hours=" + (h !== null ? h : state.committedHours);
  }

  async function exportPDF(ev) {
    if (ev) ev.preventDefault();
    if (state.exportBusy) return;
    const hours = readHours() !== null ? readHours() : state.committedHours;
    setExportBusy(true);
    toast("Generating the PDF — the server re-runs the analysis, so this can take ~30 s.", "info", 5000);

    const ctrl = beginRequest("export");
    const timer = setTimeout(() => ctrl.abort(), 180000);
    try {
      const res = await fetch("/export-pdf?hours=" + hours, { signal: ctrl.signal });
      if (!res.ok) {
        let detail = "PDF generation failed (HTTP " + res.status + ").";
        try { const b = await res.json(); if (b && b.detail) detail = String(b.detail); } catch (_) {}
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = el("a");
      a.href = url;
      a.download = "studyflow-plan-" + hours + "h.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast("PDF downloaded — " + hours + " hour plan.", "success");
    } catch (err) {
      if (err.name === "AbortError") toast("PDF generation timed out. Please try again.", "danger", 9000);
      else toast("PDF failed: " + (err.message || err), "danger", 9000);
    } finally {
      clearTimeout(timer);
      state.ctrl.export = null;
      setExportBusy(false);
    }
  }

  /* ── hours control ───────────────────────────────────────────── */
  function readHours() {
    const input = $("#hours-input");
    const value = Number(input.value);
    const valid = Number.isInteger(value) && value >= 1 && value <= 500;
    input.classList.toggle("is-invalid", !valid);
    return valid ? value : null;
  }

  function rebuild() {
    const hours = readHours();
    if (hours === null) { toast("Enter a whole number of hours between 1 and 500.", "warning"); return; }
    loadPlan(hours);
  }

  /* ── wire up ─────────────────────────────────────────────────── */
  const fromUrl = Number(new URLSearchParams(location.search).get("hours"));
  const initial = Number.isInteger(fromUrl) && fromUrl >= 1 && fromUrl <= 500 ? fromUrl : 20;
  $("#hours-input").value = initial;
  state.committedHours = initial;
  markSelectedPreset(initial);
  syncExportHref();

  $("#rebuild-btn").addEventListener("click", rebuild);
  $("#hours-input").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); rebuild(); } });
  $("#hours-input").addEventListener("input", () => {
    const input = $("#hours-input");
    if (input.classList.contains("is-invalid")) readHours();
    syncExportHref();
  });
  $$("[data-hours]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("#hours-input").value = btn.getAttribute("data-hours");
      rebuild();
    });
  });
  $$("[data-retry]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const which = btn.getAttribute("data-retry");
      if (which === "plan") loadPlan(readHours() !== null ? readHours() : state.committedHours);
      if (which === "weightages") loadWeightages();
      if (which === "frequencies") loadFrequencies();
    });
  });
  $("#export-link").addEventListener("click", exportPDF);

  loadWeightages();
  loadFrequencies();
  loadPlan(initial);
})();