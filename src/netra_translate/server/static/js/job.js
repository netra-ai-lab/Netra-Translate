import { api } from "./api.js";
import { num, t } from "./i18n.js";
import { buildHits, buildTranslated, fitSheet, layoutPage, loadPixels, pagePng } from "./render.js";
import { copyText, download, h, icon, iconButton, toast } from "./util.js";

const TEXT_TYPES = new Set(["heading", "paragraph", "caption", "page_header", "page_footer"]);
const DIRECTIONS = ["auto", "km2en", "en2km"];
const MENU_FORMATS = ["docx", "html", "md", "txt", "json"];
const ZOOMS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2];

export function renderJob(root, jobId) {
  let disposed = false;
  let pollTimer = null;
  let cleanupView = null;
  let progressEls = null;

  async function poll() {
    if (disposed) return;
    let job;
    try {
      job = (await api.job(jobId)).job;
    } catch (e) {
      if (e.status === 404) return renderMissing();
      pollTimer = setTimeout(poll, 3000);
      return;
    }
    if (job.status === "done") {
      try {
        const result = await api.result(jobId);
        if (!disposed) {
          progressEls = null;
          cleanupView = renderDocument(root, job, result, retranslate);
        }
      } catch {
        toast(t("err.generic"));
        pollTimer = setTimeout(poll, 3000);
      }
      return;
    }
    renderProgress(job);
    if (job.status !== "error") pollTimer = setTimeout(poll, 1000);
  }

  // Re-translation (new direction, or a retry) runs on the server's worker;
  // this page goes back to polling, so a reload resumes it too.
  async function retranslate(direction) {
    try {
      await api.retranslate(jobId, direction);
    } catch (e) {
      toast(e.message || t("err.generic"));
      return false;
    }
    if (cleanupView) { cleanupView(); cleanupView = null; }
    progressEls = null;
    clearTimeout(pollTimer);
    poll();
    return true;
  }

  function renderMissing() {
    root.replaceChildren(h("section", { class: "wrap" }, h("div", { class: "processing panel" },
      h("p", { class: "eyebrow muted2" }, t("status.error")),
      h("h1", { class: "h3" }, t("proc.missing")),
      h("p", { class: "actions" }, h("a", { class: "pill", href: "#/" }, t("proc.back"))))));
  }

  function renderProgress(job) {
    if (!progressEls) {
      const step = (key) => h("li", { class: "step" }, h("span", { class: "step-dot", "aria-hidden": "true" }),
        h("span", { class: "step-name" }, t(key)), h("span", { class: "step-meta meta" }));
      progressEls = {
        steps: [step("proc.step.ocr"), step("proc.step.translate")],
        bar: h("div", { class: "bar" }, h("span")),
        meta: h("p", { class: "meta", role: "status" }),
        note: h("p", { class: "note" }),
        actions: h("div", { class: "actions" }),
      };
      const { steps, bar, meta, note, actions } = progressEls;
      root.replaceChildren(h("section", { class: "wrap" }, h("div", { class: "processing panel" },
        h("h1", { class: "h3 proc-name" }, job.filename),
        h("ol", { class: "steps" }, steps), bar, meta, note, actions)));
    }
    const { steps, bar, meta, note, actions } = progressEls;
    if (job.status === "error") {
      steps.forEach((s) => s.classList.remove("active"));
      bar.hidden = true;
      meta.textContent = t("proc.failed");
      note.replaceChildren(h("span", { class: "error-text" }, job.error || ""));
      actions.replaceChildren(
        job.ocr_done
          ? h("button", { class: "pill pill-primary", type: "button",
            onclick: () => retranslate(job.options.direction) }, icon("reset"), t("proc.retry"))
          : h("a", { class: "pill pill-primary", href: "#/" }, t("proc.reupload")),
        h("a", { class: "pill", href: "#/" }, t("proc.back")));
      return;
    }
    const { phase, done, total } = job.progress;
    const translating = phase === "translate";
    steps[0].classList.toggle("active", !translating);
    steps[0].classList.toggle("done", translating);
    steps[1].classList.toggle("active", translating);
    const counter = total && done ? `${num(done)} / ${num(total)}` : "";
    steps[0].lastChild.textContent = translating ? "" : counter;
    steps[1].lastChild.textContent = translating ? counter : "";

    bar.hidden = false;
    bar.classList.toggle("indeterminate", job.status === "queued" || !total || done === 0);
    bar.firstChild.style.width = total ? `${Math.max(4, (done / total) * 100)}%` : "0";
    if (job.status === "queued") meta.textContent = t("proc.queued");
    else if (!total || done === 0) meta.textContent = t("proc.starting");
    else meta.textContent = t(translating ? "proc.blocks" : "proc.page", { done: num(done), total: num(total) });
    note.textContent = t("proc.note");
    actions.replaceChildren();
  }

  poll();
  return () => {
    disposed = true;
    clearTimeout(pollTimer);
    if (cleanupView) cleanupView();
  };
}

// ════════════════════════════════════════════════════════════════════════
// Document view: the scan and its translated copy, page by page
// ════════════════════════════════════════════════════════════════════════

function segmented(label, options, value, onpick) {
  const buttons = options.map(([v, text, extra = {}]) => h("button", {
    type: "button", "aria-pressed": String(v === value), dataset: { value: v },
    onclick: () => onpick(v), ...extra }, text));
  const el = h("div", { class: "seg", role: "group", "aria-label": label }, buttons);
  el.set = (v) => buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === v)));
  return el;
}

function renderDocument(root, job, doc, retranslate) {
  const pages = doc.pages;
  const blocks = doc.blocks;
  const assetUrl = (id) => api.assetUrl(job.id, id);
  const narrow = window.matchMedia("(max-width: 899px)");
  const state = { view: narrow.matches ? "translated" : "both", zoom: 3, current: 0, bilingual: false };
  const current = job.direction || job.options.direction;

  // ── toolbar ─────────────────────────────────────────────────────────
  const dirSeg = segmented(t("doc.direction"),
    DIRECTIONS.map((d) => [d, t(`dir.short.${d}`), { title: t(`dir.${d}`) }]), current,
    async (d) => {
      if (d === current) return;
      dirSeg.set(d);
      dirSeg.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      if (!(await retranslate(d))) {
        dirSeg.set(current);
        dirSeg.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      }
    });

  const viewSeg = segmented(t("doc.view"), [
    ["original", t("doc.original")],
    ["both", t("doc.sideBySide"), { class: "wide-only" }],
    ["translated", t("doc.translation")],
  ], state.view, setView);

  const zoomLabel = h("button", { class: "zoom-label meta", type: "button", title: t("doc.zoomFit"),
    onclick: () => setZoom(3) });
  const zoom = h("div", { class: "zoom" },
    iconButton("minus", t("doc.zoomOut"), () => setZoom(state.zoom - 1)),
    zoomLabel,
    iconButton("plus", t("doc.zoomIn"), () => setZoom(state.zoom + 1)));

  const bilingual = h("input", { type: "checkbox", onchange: () => { state.bilingual = bilingual.checked; } });
  const menuItem = (label, ext, onclick) => h("button", { type: "button", role: "menuitem",
    onclick: () => { closeMenu(); onclick(); } }, h("span", {}, label), h("span", { class: "meta" }, ext));
  const menuList = h("div", { class: "menu-list", role: "menu", hidden: true,
    onclick: (e) => e.stopPropagation() },
    h("p", { class: "menu-head eyebrow muted2" }, t("doc.asPages")),
    menuItem(t("fmt.pdf"), ".pdf", printPdf),
    menuItem(t("fmt.png"), ".png", savePng),
    h("p", { class: "menu-head eyebrow muted2" }, t("doc.asText")),
    MENU_FORMATS.map((f) => menuItem(t(`fmt.${f}`), `.${f}`,
      () => download(api.exportUrl(job.id, f, state.bilingual)))),
    h("label", { class: "check menu-check" }, bilingual, h("span", {}, t("doc.bilingual"))));
  const downloadBtn = h("button", { class: "pill pill-primary pill-sm", type: "button", "aria-haspopup": "menu",
    "aria-expanded": "false", onclick: (e) => { e.stopPropagation(); menuList.hidden ? openMenu() : closeMenu(); } },
  icon("download"), t("doc.download"), icon("chevDown"));
  function openMenu() { menuList.hidden = false; downloadBtn.setAttribute("aria-expanded", "true"); }
  function closeMenu() { menuList.hidden = true; downloadBtn.setAttribute("aria-expanded", "false"); }

  const toolbar = h("div", { class: "toolbar" }, h("div", { class: "toolbar-inner" },
    h("a", { class: "icon-btn", href: "#/", title: t("proc.back"), "aria-label": t("proc.back") }, icon("chevLeft")),
    h("div", { class: "doc-title" },
      h("strong", { title: job.filename }, job.filename),
      h("span", { class: "meta" }, t(pages.length === 1 ? "doc.onePage" : "doc.pages", { n: num(pages.length) }))),
    dirSeg,
    h("span", { class: "spacer" }),
    viewSeg,
    zoom,
    iconButton("copy", t("doc.copy"), copyAll),
    h("div", { class: "menu" }, downloadBtn, menuList)));

  // ── pages ───────────────────────────────────────────────────────────
  const byPage = new Map(pages.map((p) => [p.index, []]));
  for (const b of blocks) byPage.get(b.page)?.push(b);
  const layouts = new Map();

  const rows = pages.map((p) => {
    const ratio = p.width && p.height ? `${p.width} / ${p.height}` : "1 / 1.414";
    const hits = h("div", { class: "hits" });
    const original = h("div", { class: "sheet sheet-src", style: `aspect-ratio:${ratio}` },
      p.image ? h("img", { src: assetUrl(p.image), alt: t("doc.pageLabel", { n: num(p.index + 1) }),
        loading: "lazy", draggable: "false" }) : null,
      hits);
    const translated = h("div", { class: "sheet sheet-tr", style: `aspect-ratio:${ratio}` });
    const row = h("section", { class: "page-row", dataset: { page: p.index },
      "aria-label": t("doc.pageLabel", { n: num(p.index + 1) }) },
    h("div", { class: "pane pane-src" }, original),
    h("div", { class: "pane pane-tr" }, translated),
    pages.length > 1 ? h("p", { class: "page-num meta" }, t("doc.page", { n: num(p.index + 1), total: num(pages.length) })) : null);
    row._parts = { page: p, hits, translated, built: false };
    return row;
  });

  // Pages are laid out when they come near the screen.
  async function build(row) {
    const parts = row._parts;
    if (parts.built) return;
    parts.built = true;
    const p = parts.page;
    if (!p.width || !p.height) return;
    const px = p.image ? await loadPixels(assetUrl(p.image)) : null;
    const layout = layoutPage(p, byPage.get(p.index) || [], px);
    layouts.set(p.index, layout);
    buildTranslated(parts.translated, p, layout, assetUrl);
    buildHits(parts.hits, p, layout);
    requestAnimationFrame(() => fitSheet(parts.translated));
  }

  const near = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) build(e.target);
  }, { rootMargin: "800px 0px" });
  // The page in the middle of the screen is the one PNG export saves.
  const seen = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) state.current = Number(e.target.dataset.page);
  }, { rootMargin: "-45% 0px -45% 0px" });
  rows.forEach((r) => { near.observe(r); seen.observe(r); });

  const pagesEl = h("div", { class: "pages", "aria-live": "off" },
    rows.length ? rows : h("p", { class: "empty" }, t("doc.empty")));
  const stage = h("div", { class: "doc-stage" }, pagesEl);

  // ── line linking ────────────────────────────────────────────────────
  // Hovering a line lights up the same line on both sheets; clicking keeps it lit.
  let hovered = null;
  let selected = null;
  const mark = (row, key, cls, on) => {
    if (!row || !key) return;
    row.querySelectorAll(`[data-line="${CSS.escape(key)}"]`).forEach((el) => el.classList.toggle(cls, on));
  };
  function lineAt(target) {
    const el = target.closest?.("[data-line]");
    return el ? { row: el.closest(".page-row"), key: el.dataset.line } : null;
  }
  pagesEl.addEventListener("mouseover", (e) => {
    const hit = lineAt(e.target);
    if (hovered && (!hit || hit.key !== hovered.key)) { mark(hovered.row, hovered.key, "hl", false); hovered = null; }
    if (hit && !hovered) { hovered = hit; mark(hit.row, hit.key, "hl", true); }
  });
  pagesEl.addEventListener("mouseleave", () => {
    if (hovered) { mark(hovered.row, hovered.key, "hl", false); hovered = null; }
  });
  pagesEl.addEventListener("click", (e) => {
    if (window.getSelection()?.toString()) return;
    const hit = lineAt(e.target);
    if (selected) mark(selected.row, selected.key, "sel", false);
    selected = hit && (!selected || hit.key !== selected.key) ? hit : null;
    if (selected) mark(selected.row, selected.key, "sel", true);
  });

  // ── view + zoom ─────────────────────────────────────────────────────
  function setView(v) {
    state.view = v;
    viewSeg.set(v);
    stage.dataset.view = v;
    requestAnimationFrame(() => rows.forEach((r) => r._parts.built && fitSheet(r._parts.translated)));
  }

  function setZoom(i) {
    state.zoom = Math.max(0, Math.min(ZOOMS.length - 1, i));
    stage.style.setProperty("--zoom", ZOOMS[state.zoom]);
    zoomLabel.textContent = `${Math.round(ZOOMS[state.zoom] * 100)}%`;
    zoom.firstChild.disabled = state.zoom === 0;
    zoom.lastChild.disabled = state.zoom === ZOOMS.length - 1;
  }

  const onNarrow = () => { if (narrow.matches && state.view === "both") setView("translated"); };
  narrow.addEventListener("change", onNarrow);

  // ── output ──────────────────────────────────────────────────────────
  function plainText() {
    return blocks.map((b) => {
      if (TEXT_TYPES.has(b.type)) return b.text || "";
      if (b.type === "table") return (b.rows || []).map((r) => r.join("\t")).join("\n");
      return "";
    }).filter((s) => s.trim()).join("\n\n");
  }

  async function copyAll() {
    if (await copyText(plainText())) toast(t("doc.copied"));
  }

  async function savePng() {
    const row = rows[state.current];
    if (!row) return;
    await build(row);
    const layout = layouts.get(state.current);
    if (!layout) return;
    const blob = await pagePng(row._parts.page, layout, assetUrl);
    if (!blob) return toast(t("err.generic"));
    const url = URL.createObjectURL(blob);
    const a = h("a", { href: url,
      download: `${job.filename.replace(/\.[^.]+$/, "")}_translated${pages.length > 1 ? `_p${state.current + 1}` : ""}.png` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // Printing (Save as PDF) prints the translated sheets only, so every one has
  // to be laid out and visible first.
  async function printPdf() {
    if (state.view === "original") setView("translated");
    await Promise.all(rows.map(build));
    await new Promise((r) => requestAnimationFrame(r));
    rows.forEach((r) => fitSheet(r._parts.translated));
    window.print();
  }
  const beforePrint = () => rows.forEach((r) => build(r));
  window.addEventListener("beforeprint", beforePrint);

  const onDocClick = () => closeMenu();
  const onKey = (e) => { if (e.key === "Escape") closeMenu(); };
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);

  // ── mount ───────────────────────────────────────────────────────────
  root.replaceChildren(toolbar, stage);
  setView(state.view);
  setZoom(state.zoom);

  return () => {
    near.disconnect();
    seen.disconnect();
    narrow.removeEventListener("change", onNarrow);
    window.removeEventListener("beforeprint", beforePrint);
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKey);
  };
}
