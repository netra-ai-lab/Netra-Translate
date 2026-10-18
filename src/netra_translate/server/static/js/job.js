import { api } from "./api.js";
import { num, t } from "./i18n.js";
import { copyText, download, h, icon, iconButton, toast } from "./util.js";

const TEXT_TYPES = new Set(["heading", "paragraph", "caption", "page_header", "page_footer"]);
const DIRECTIONS = ["auto", "km2en", "en2km"];
const MENU_FORMATS = ["docx", "md", "html", "txt", "json"];

function typeKey(b) {
  return b.type === "heading" ? `heading-${b.level || 1}` : b.type;
}

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
    root.replaceChildren(h("section", { class: "wrap" }, h("div", { class: "processing" },
      h("p", { class: "eyebrow muted2" }, t("status.error")),
      h("h1", { class: "h2" }, t("proc.missing")),
      h("p", { class: "note" }, h("a", { href: "#/" }, `← ${t("proc.back")}`)))));
  }

  function renderProgress(job) {
    if (!progressEls) {
      progressEls = {
        eyebrow: h("p", { class: "eyebrow muted2" }),
        bar: h("div", { class: "bar" }, h("span")),
        meta: h("p", { class: "meta", role: "status" }),
        note: h("p", { class: "note" }),
        actions: h("div", { class: "actions" }),
      };
      const { eyebrow, bar, meta, note, actions } = progressEls;
      root.replaceChildren(h("section", { class: "wrap" }, h("div", { class: "processing" },
        eyebrow, h("h1", { class: "h2" }, job.filename), bar, meta, note, actions)));
    }
    const { eyebrow, bar, meta, note, actions } = progressEls;
    if (job.status === "error") {
      eyebrow.textContent = t("status.error");
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
    eyebrow.textContent = t(`proc.eyebrow.${phase === "translate" ? "translate" : "ocr"}`);
    bar.hidden = false;
    bar.classList.toggle("indeterminate", job.status === "queued" || !total || done === 0);
    bar.firstChild.style.width = total ? `${Math.max(4, (done / total) * 100)}%` : "0";
    if (job.status === "queued") meta.textContent = t("proc.queued");
    else if (!total || done === 0) meta.textContent = t("proc.starting");
    else meta.textContent = t(phase === "translate" ? "proc.blocks" : "proc.page", { done: num(done), total: num(total) });
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
// Document view: original page on the left, translation on the right
// ════════════════════════════════════════════════════════════════════════

function renderDocument(root, job, doc, retranslate) {
  const pages = doc.pages;
  const blocks = doc.blocks;
  const state = { page: blocks[0] ? blocks[0].page : 0, activeId: null, bilingual: false };

  // ── toolbar ─────────────────────────────────────────────────────────
  const direction = h("select", { class: "select", "aria-label": t("doc.direction"),
    onchange: async () => {
      direction.disabled = true;
      if (!(await retranslate(direction.value))) {
        direction.value = job.direction || job.options.direction;
        direction.disabled = false;
      }
    } }, DIRECTIONS.map((d) => h("option", { value: d, selected: d === (job.direction || job.options.direction) }, t(`dir.${d}`))));

  const bilingual = h("input", { type: "checkbox", onchange: () => { state.bilingual = bilingual.checked; } });
  const menuList = h("div", { class: "menu-list", role: "menu", hidden: true,
    onclick: (e) => e.stopPropagation() },
    h("label", { class: "check" }, bilingual, h("span", {}, t("doc.bilingual"))),
    MENU_FORMATS.map((f) => h("button", { type: "button", role: "menuitem",
      onclick: () => { closeMenu(); download(api.exportUrl(job.id, f, state.bilingual)); } },
    h("span", {}, t(`fmt.${f}`)), h("span", { class: "meta" }, `.${f}`))));
  const moreBtn = h("button", { class: "pill pill-sm", type: "button", "aria-haspopup": "menu", "aria-expanded": "false",
    onclick: (e) => { e.stopPropagation(); menuList.hidden ? openMenu() : closeMenu(); } }, t("doc.more"), icon("chevDown"));
  function openMenu() { menuList.hidden = false; moreBtn.setAttribute("aria-expanded", "true"); }
  function closeMenu() { menuList.hidden = true; moreBtn.setAttribute("aria-expanded", "false"); }
  const onDocClick = () => closeMenu();
  const onKey = (e) => { if (e.key === "Escape") closeMenu(); };
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);

  const toolbar = h("div", { class: "toolbar" }, h("div", { class: "toolbar-inner" },
    h("a", { class: "icon-btn", href: "#/", title: t("proc.back"), "aria-label": t("proc.back") }, icon("chevLeft")),
    h("div", { class: "doc-title" },
      h("strong", { title: job.filename }, job.filename),
      h("span", { class: "meta" }, `${t("col.pages")}: ${num(pages.length)}`)),
    direction,
    h("span", { class: "divider", "aria-hidden": "true" }),
    h("div", { class: "tool-group" },
      h("button", { class: "pill pill-sm", type: "button", onclick: copyAll }, icon("copy"), t("doc.copy")),
      h("div", { class: "menu" }, moreBtn, menuList),
      h("button", { class: "pill pill-primary pill-sm", type: "button",
        onclick: () => download(api.exportUrl(job.id, "docx", false)) }, icon("download"), t("doc.download")))));

  // ── page viewer ─────────────────────────────────────────────────────
  const pageImg = h("img", { alt: t("doc.original"), draggable: "false" });
  const overlay = h("div", { class: "overlay" });
  const frame = h("div", { class: "page-frame" }, h("div", { class: "page-stage" }, pageImg, overlay));
  const pageLabel = h("span", { class: "meta" });
  const prevBtn = iconButton("chevLeft", t("doc.prev"), () => showPage(state.page - 1));
  const nextBtn = iconButton("chevRight", t("doc.next"), () => showPage(state.page + 1));
  const thumbs = h("div", { class: "thumbs", hidden: pages.length < 2 },
    pages.map((p) => h("button", { class: "thumb", type: "button",
      "aria-label": t("doc.pageLabel", { n: num(p.index + 1) }), onclick: () => showPage(p.index) },
    h("img", { src: p.image ? api.assetUrl(job.id, p.image) : "", alt: "", loading: "lazy" }))));
  const viewer = h("aside", { class: "viewer", "aria-label": t("doc.original") },
    h("div", { class: "viewer-head" },
      h("span", { class: "eyebrow muted2" }, t("doc.original")),
      h("div", { class: "tool-group", hidden: pages.length < 2 }, prevBtn, pageLabel, nextBtn)),
    frame, thumbs);

  function showPage(index) {
    if (index < 0 || index >= pages.length) return;
    const changed = index !== state.page || !pageImg.getAttribute("src");
    state.page = index;
    const p = pages[index];
    if (changed) pageImg.src = p.image ? api.assetUrl(job.id, p.image) : "";
    pageLabel.textContent = t("doc.page", { n: num(index + 1), total: num(pages.length) });
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === pages.length - 1;
    thumbs.querySelectorAll(".thumb").forEach((el, i) => el.setAttribute("aria-current", String(i === index)));
    renderOverlay();
  }

  function renderOverlay() {
    const p = pages[state.page];
    if (!p || !p.width) return overlay.replaceChildren();
    overlay.replaceChildren(...blocks
      .filter((b) => b.page === state.page && b.bbox)
      .map((b) => {
        const [x1, y1, x2, y2] = b.bbox;
        return h("button", {
          class: `ov${b.id === state.activeId ? " active" : ""}`, type: "button", dataset: { id: b.id, type: b.type },
          style: `left:${(x1 / p.width) * 100}%;top:${(y1 / p.height) * 100}%;`
            + `width:${((x2 - x1) / p.width) * 100}%;height:${((y2 - y1) / p.height) * 100}%`,
          "aria-label": t(`type.${typeKey(b)}`),
          onclick: () => focusBlock(b.id),
          onmouseenter: () => hover(b.id, true),
          onmouseleave: () => hover(b.id, false),
        }, h("span", { class: "ov-tag" }, t(`type.${typeKey(b)}`)));
      }));
  }

  // ── translation ─────────────────────────────────────────────────────
  const showSource = h("input", { type: "checkbox", checked: true,
    onchange: () => docEl.classList.toggle("hide-source", !showSource.checked) });
  const docEl = h("article", { class: "doc" });
  const docCol = h("section", { "aria-label": t("doc.translation") },
    h("div", { class: "doc-head" },
      h("span", { class: "eyebrow muted2" }, t("doc.translation")),
      h("label", { class: "check meta" }, showSource, h("span", {}, t("doc.showSource")))),
    docEl);

  function renderDoc() {
    const children = [];
    let prevPage = null;
    for (const b of blocks) {
      if (pages.length > 1 && b.page !== prevPage) {
        children.push(h("div", { class: "page-break eyebrow" }, t("doc.pageLabel", { n: num(b.page + 1) })));
      }
      prevPage = b.page;
      children.push(renderBlock(b));
    }
    if (!blocks.length) children.push(h("p", { class: "empty" }, t("doc.empty")));
    docEl.replaceChildren(...children);
  }

  function table(rows) {
    return h("div", { class: "tbl-wrap" }, h("table", {}, h("tbody", {},
      rows.map((row) => h("tr", {}, row.map((cell) => h("td", {}, cell)))))));
  }

  function renderBlock(b) {
    const key = typeKey(b);
    const body = h("div", { class: "block-body" });
    if (TEXT_TYPES.has(b.type)) {
      body.append(b.text ? h("div", { class: "text" }, b.text) : h("div", { class: "text untranslated" }, t("doc.notTranslated")));
      if (b.source_text && b.source_text !== b.text) body.append(h("div", { class: "source" }, b.source_text));
    } else if (b.type === "table") {
      body.append(table(b.rows || []));
      if (b.source_rows) body.append(h("div", { class: "source" }, table(b.source_rows)));
    } else if (b.image) {
      body.append(h("figure", {}, h("img", { src: api.assetUrl(job.id, b.image), alt: t(`type.${key}`), loading: "lazy" })));
    }
    return h("div", {
      class: `block b-${key} align-${b.align || "left"}`, dataset: { id: b.id },
      onclick: () => setActive(b.id),
      onmouseenter: () => hover(b.id, true),
      onmouseleave: () => hover(b.id, false),
    }, h("div", { class: "block-label" }, t(`type.${key}`)), body);
  }

  // ── linking boxes and blocks ────────────────────────────────────────
  const sel = (id) => `[data-id="${CSS.escape(id)}"]`;

  function hover(id, on) {
    docEl.querySelector(`.block${sel(id)}`)?.classList.toggle("hover", on);
    overlay.querySelector(`.ov${sel(id)}`)?.classList.toggle("hover", on);
  }

  function setActive(id) {
    state.activeId = id;
    docEl.querySelectorAll(".block.active").forEach((el) => el.classList.remove("active"));
    docEl.querySelector(`.block${sel(id)}`)?.classList.add("active");
    const b = blocks.find((x) => x.id === id);
    if (b && b.page !== state.page) showPage(b.page);
    else renderOverlay();
    const ov = overlay.querySelector(`.ov${sel(id)}`);
    if (ov) scrollIntoFrame(ov);
  }

  function scrollIntoFrame(ov) {
    const f = frame.getBoundingClientRect();
    const r = ov.getBoundingClientRect();
    if (r.top < f.top || r.bottom > f.bottom) frame.scrollTop += r.top - f.top - f.height / 3;
  }

  function focusBlock(id) {
    setActive(id);
    docEl.querySelector(`.block${sel(id)}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

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

  // ── mount ───────────────────────────────────────────────────────────
  root.replaceChildren(toolbar, h("div", { class: "wrap" }, h("div", { class: "split" }, viewer, docCol)));
  renderDoc();
  showPage(state.page);

  return () => {
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKey);
  };
}
