import { api, mine } from "./api.js";
import { num, t } from "./i18n.js";
import { formatDate, h, icon, iconButton, toast } from "./util.js";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp,application/pdf,image/*";
const DIRECTIONS = ["auto", "km2en", "en2km"];

function statusLabel(job) {
  if (job.status === "running") return t(`status.${job.progress.phase || "ocr"}`);
  return t(`status.${job.status}`);
}

export function renderHome(root, info) {
  let disposed = false;
  let pollTimer = null;
  let file = null;
  const limits = info?.limits || { max_upload_mb: 50, max_pages: 100, job_ttl_hours: 24 };
  const demo = !!info?.demo;
  const layoutAvailable = info ? info.layout_available : true;

  // ── upload card ─────────────────────────────────────────────────────
  const input = h("input", { type: "file", accept: ACCEPT, "aria-label": t("drop.label") });
  const dropTitle = h("p", { class: "drop-title", html: t("drop.title") });
  const dropMeta = h("p", { class: "meta" }, t("drop.meta", { mb: limits.max_upload_mb, pages: limits.max_pages }));
  const drop = h("label", { class: "drop" },
    h("span", { class: "drop-icon" }, icon("upload")), dropTitle, dropMeta, input);

  const direction = h("select", { class: "select", "aria-label": t("opt.direction") },
    DIRECTIONS.map((d) => h("option", { value: d }, t(`dir.${d}`))));
  const layout = h("input", { type: "checkbox", disabled: !layoutAvailable,
    checked: layoutAvailable && !!info?.defaults?.layout });
  const submit = h("button", { class: "pill pill-primary", type: "submit" }, t("opt.submit"));
  const error = h("p", { class: "error-text", role: "alert" });
  const errorRow = h("div", { class: "upload-error", hidden: true }, error);

  const form = h("form", { class: "panel upload", onsubmit: (e) => { e.preventDefault(); send(); } },
    drop,
    h("div", { class: "upload-bar" },
      h("label", { class: "inline-field" }, h("span", {}, t("opt.direction")), direction),
      h("label", { class: "check", title: layoutAvailable ? t("opt.layoutDesc") : t("opt.layoutMissing") },
        layout, h("span", {}, t("opt.layout")), h("span", { class: "hint", "aria-hidden": "true" }, "?")),
      h("span", { class: "spacer" }),
      submit),
    errorRow);

  function choose(f) {
    if (!f) return;
    file = f;
    dropTitle.replaceChildren(h("span", { class: "drop-file" }, f.name || "pasted-image.png"));
    dropMeta.textContent = t("drop.change");
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
    body.append("direction", direction.value);
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
    list.replaceChildren(h("table", { class: "index" },
      h("thead", {}, h("tr", {},
        h("th", { scope: "col" }, t("col.name")),
        h("th", { scope: "col", class: "hide-sm" }, t("col.pages")),
        h("th", { scope: "col" }, t("col.status")),
        h("th", { scope: "col", class: "hide-sm" }, t("col.created")),
        h("th", { scope: "col", class: "act" }, h("span", { class: "sr-only" }, t("col.actions"))))),
      h("tbody", {}, jobs.map(row))));
  }

  function row(job) {
    const open = () => { location.hash = `#/job/${job.id}`; };
    const del = iconButton("trash", t("recent.delete"), async (e) => {
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
    });
    return h("tr", { onclick: open, tabindex: "0", onkeydown: (e) => { if (e.key === "Enter") open(); } },
      h("td", { class: "name" }, h("a", { href: `#/job/${job.id}`, onclick: (e) => e.stopPropagation() }, job.filename)),
      h("td", { class: "num-cell hide-sm" }, num(job.pages)),
      h("td", {}, h("span", { class: `status status-${job.status}` }, statusLabel(job))),
      h("td", { class: "meta hide-sm" }, formatDate(job.created)),
      h("td", { class: "act" }, del, h("span", { class: "arrow", "aria-hidden": "true" }, " →")));
  }

  // ── mount ───────────────────────────────────────────────────────────
  const ttl = limits.job_ttl_hours;
  root.replaceChildren(h("section", { class: "wrap page" },
    h("div", { class: "page-head" },
      h("div", {}, h("h1", { class: "h2" }, t("home.title")), h("p", { class: "lede" }, t("home.lede")))),
    form,
    demo ? h("p", { class: "notice", html: t("home.demo", { h: ttl, pages: limits.max_pages, mb: limits.max_upload_mb }) }) : null,
    h("div", { class: "list-head" },
      h("h2", { class: "h3" }, t("recent.title")),
      h("p", { class: "meta muted2" }, t(demo ? "recent.noteDemo" : "recent.note", { h: ttl }))),
    list));
  refresh();

  return () => {
    disposed = true;
    clearTimeout(pollTimer);
    window.removeEventListener("dragover", onDragOver);
    window.removeEventListener("dragleave", onDragLeave);
    window.removeEventListener("drop", onDrop);
    window.removeEventListener("paste", onPaste);
  };
}
