import { api, mine } from "./api.js";
import { num, t } from "./i18n.js";
import { formatDate, h, icon, iconButton, toast } from "./util.js";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp,application/pdf,image/*";

function statusLabel(job) {
  if (job.status === "running") return t(`status.${job.progress.phase || "ocr"}`);
  return t(`status.${job.status}`);
}

// The language row maps onto the API's three directions.
function directionOf(from) {
  return from === "km" ? "km2en" : from === "en" ? "en2km" : "auto";
}

export function renderHome(root, info) {
  let disposed = false;
  let pollTimer = null;
  let file = null;
  let previewUrl = null;
  const limits = info?.limits || { max_upload_mb: 50, max_pages: 100, job_ttl_hours: 24 };
  const demo = !!info?.demo;
  const layoutAvailable = info ? info.layout_available : true;

  // ── upload card ─────────────────────────────────────────────────────
  const input = h("input", { type: "file", accept: ACCEPT, "aria-label": t("drop.label") });
  const dropBody = h("div", { class: "drop-body" });
  const drop = h("label", { class: "drop" }, dropBody, input);

  function showEmpty() {
    dropBody.replaceChildren(
      h("span", { class: "drop-icon" }, icon("upload")),
      h("p", { class: "drop-title", html: t("drop.title") }),
      h("p", { class: "meta" }, t("drop.meta", { mb: limits.max_upload_mb, pages: limits.max_pages })));
  }

  const from = h("select", { class: "select", "aria-label": t("lang.from"), onchange: syncTo },
    ["auto", "km", "en"].map((v) => h("option", { value: v }, t(`lang.${v}`))));
  const to = h("select", { class: "select", "aria-label": t("lang.to"), onchange: syncFrom });
  const swap = iconButton("swap", t("lang.swap"), () => {
    from.value = from.value === "km" ? "en" : "km";
    syncTo();
  });

  // Two languages: picking one side fixes the other. "Detect" translates each
  // block into the other language, whichever it is.
  function syncTo() {
    const v = from.value;
    to.replaceChildren(...(v === "auto"
      ? [h("option", { value: "auto" }, t("lang.other"))]
      : [h("option", { value: "en", selected: v === "km" }, t("lang.en")),
        h("option", { value: "km", selected: v === "en" }, t("lang.km"))]));
    to.disabled = v === "auto";
  }
  function syncFrom() { from.value = to.value === "en" ? "km" : "en"; syncTo(); }
  syncTo();

  const layout = h("input", { type: "checkbox", disabled: !layoutAvailable,
    checked: layoutAvailable && !!info?.defaults?.layout });
  const submit = h("button", { class: "pill pill-primary pill-lg", type: "submit" }, t("opt.submit"));
  const error = h("p", { class: "error-text", role: "alert" });
  const errorRow = h("div", { class: "upload-error", hidden: true }, error);

  const form = h("form", { class: "panel upload", onsubmit: (e) => { e.preventDefault(); send(); } },
    drop,
    h("div", { class: "upload-bar" },
      h("div", { class: "langs" }, from, swap, to),
      h("span", { class: "spacer" }),
      submit),
    h("details", { class: "advanced" },
      h("summary", {}, t("opt.advanced")),
      h("label", { class: "check" }, layout, h("span", {}, t("opt.layout"))),
      h("p", { class: "meta muted" }, layoutAvailable ? t("opt.layoutDesc") : t("opt.layoutMissing"))),
    errorRow);

  function choose(f) {
    if (!f) return;
    file = f;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = f.type?.startsWith("image/") && !/tiff/.test(f.type) ? URL.createObjectURL(f) : null;
    dropBody.replaceChildren(
      h("div", { class: "drop-preview" }, previewUrl
        ? h("img", { src: previewUrl, alt: "" })
        : h("span", { class: "drop-icon" }, icon("file"))),
      h("p", { class: "drop-file" }, f.name || "pasted-image.png"),
      h("p", { class: "meta" }, `${(f.size / 1048576).toFixed(1)} MB · ${t("drop.change")}`));
    drop.classList.add("chosen");
    showError("");
  }

  function showError(msg) {
    error.textContent = msg;
    errorRow.hidden = !msg;
  }

  input.addEventListener("change", () => choose(input.files[0]));

  // Drop anywhere on the page, not only on the card.
  function onDragOver(e) {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    drop.classList.add("dragging");
  }
  function onDragLeave(e) { if (!e.relatedTarget) drop.classList.remove("dragging"); }
  function onDrop(e) {
    if (!e.dataTransfer?.files?.length) return;
    e.preventDefault();
    drop.classList.remove("dragging");
    choose(e.dataTransfer.files[0]);
  }
  function onPaste(e) {
    const item = [...(e.clipboardData?.files || [])][0];
    if (item) { e.preventDefault(); choose(item); }
  }
  window.addEventListener("dragover", onDragOver);
  window.addEventListener("dragleave", onDragLeave);
  window.addEventListener("drop", onDrop);
  window.addEventListener("paste", onPaste);

  async function send() {
    if (!file) { showError(t("opt.pick")); return; }
    showError("");
    submit.disabled = true;
    submit.textContent = t("opt.sending");
    const body = new FormData();
    body.append("file", file, file.name || "pasted-image.png");
    body.append("direction", directionOf(from.value));
    body.append("layout", layout.checked ? "true" : "false");
    try {
      const { job } = await api.upload(body);
      mine.add(job.id);
      location.hash = `#/job/${job.id}`;
    } catch (e) {
      showError(e.status === 0 ? t("err.network") : e.message || t("err.generic"));
      submit.disabled = false;
      submit.textContent = t("opt.submit");
    }
  }

  // ── recent documents ────────────────────────────────────────────────
  const list = h("div", {});

  async function loadJobs() {
    if (!demo) return (await api.jobs()).jobs;
    // On the demo server only this browser's own documents are shown.
    const jobs = [];
    for (const id of mine.ids()) {
      try {
        jobs.push((await api.job(id)).job);
      } catch (e) {
        if (e.status === 404) mine.remove(id);
        else throw e;
      }
    }
    return jobs.sort((a, b) => b.created - a.created);
  }

  async function refresh() {
    if (disposed) return;
    let jobs;
    try {
      jobs = await loadJobs();
    } catch {
      pollTimer = setTimeout(refresh, 5000);
      return;
    }
    if (disposed) return;
    renderList(jobs);
    if (jobs.some((j) => j.status === "queued" || j.status === "running")) pollTimer = setTimeout(refresh, 2000);
  }

  function renderList(jobs) {
    if (!jobs.length) {
      list.replaceChildren(h("p", { class: "empty" }, t("recent.empty")));
      return;
    }
    list.replaceChildren(h("ul", { class: "cards" }, jobs.map(card)));
  }

  function card(job) {
    const del = iconButton("trash", t("recent.delete"), async (e) => {
      e.preventDefault();
      e.stopPropagation();
      // Two clicks: the first arms the button, the second deletes.
      if (!del.classList.contains("armed")) {
        del.classList.add("armed");
        del.replaceChildren(t("recent.confirm"));
        setTimeout(() => {
          if (!del.isConnected) return;
          del.classList.remove("armed");
          del.replaceChildren(icon("trash"));
        }, 3000);
        return;
      }
      try {
        await api.deleteJob(job.id);
      } catch (err) {
        if (err.status !== 404) { toast(t("err.generic")); return; }
      }
      mine.remove(job.id);
      clearTimeout(pollTimer);
      refresh();
    }, { class: "icon-btn card-del" });
    // The first page render, once OCR has made it.
    const thumb = h("div", { class: "card-thumb" }, h("span", { class: "drop-icon" }, icon("file")));
    if (job.ocr_done || job.status === "done") {
      const img = h("img", { src: api.assetUrl(job.id, "page-0"), alt: "", loading: "lazy",
        onload: () => thumb.classList.add("has-img"), onerror: () => img.remove() });
      thumb.append(img);
    }
    return h("li", {}, h("a", { class: "card", href: `#/job/${job.id}` },
      thumb,
      h("div", { class: "card-body" },
        h("p", { class: "card-name", title: job.filename }, job.filename),
        h("p", { class: "meta muted2" },
          `${t(job.pages === 1 ? "doc.onePage" : "doc.pages", { n: num(job.pages) })} · ${formatDate(job.created)}`),
        h("div", { class: "card-foot" },
          h("span", { class: `status status-${job.status}` }, statusLabel(job)), del))));
  }

  // ── mount ───────────────────────────────────────────────────────────
  showEmpty();
  const ttl = limits.job_ttl_hours;
  root.replaceChildren(h("section", { class: "wrap page" },
    h("div", { class: "hero" },
      h("h1", { class: "h1" }, t("home.title")),
      h("p", { class: "lede muted" }, t("home.lede"))),
    form,
    demo ? h("p", { class: "notice", html: t("home.demo", { h: ttl, pages: limits.max_pages, mb: limits.max_upload_mb }) }) : null,
    h("ol", { class: "how" },
      ["how.1", "how.2", "how.3"].map((k, i) => h("li", {},
        h("span", { class: "how-n" }, String(i + 1)), h("span", {}, t(k))))),
    h("div", { class: "list-head" },
      h("h2", { class: "h3" }, t("recent.title")),
      h("p", { class: "meta muted2" }, t(demo ? "recent.noteDemo" : "recent.note", { h: ttl }))),
    list));
  refresh();

  return () => {
    disposed = true;
    clearTimeout(pollTimer);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    window.removeEventListener("dragover", onDragOver);
    window.removeEventListener("dragleave", onDragLeave);
    window.removeEventListener("drop", onDrop);
    window.removeEventListener("paste", onPaste);
  };
}
