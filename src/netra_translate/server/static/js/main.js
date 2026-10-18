import { api, setKey } from "./api.js";
import { renderApi } from "./apipage.js";
import { renderHome } from "./home.js";
import { applyStatic, t } from "./i18n.js";
import { renderJob } from "./job.js";
import { h } from "./util.js";

const view = document.getElementById("view");
let cleanup = null;
let info = null;

const engine = document.getElementById("engine-status");
let engineTimer = null;

// Header indicator: the models load in the background after start-up, so
// the first upload may wait; say so instead of looking stuck.
function showEngine() {
  clearTimeout(engineTimer);
  if (!info) {
    engine.className = "status status-error engine-status";
    engine.textContent = t("engine.offline");
    engineTimer = setTimeout(async () => { await loadInfo(); showEngine(); }, 5000);
    return;
  }
  const device = info.device_name || (info.device.startsWith("cuda") ? "GPU" : "CPU");
  const workers = info.workers || [];
  const again = (ms) => { engineTimer = setTimeout(async () => { await loadInfo(); showEngine(); }, ms); };
  if (info.workers && !workers.length) {
    // The API runs with --no-worker and no worker process has started (or all stopped).
    engine.className = "status status-running engine-status";
    engine.textContent = t("engine.noWorker");
    again(5000);
  } else if (info.models_ready) {
    engine.className = "status status-done engine-status";
    engine.textContent = workers.length > 1
      ? t("engine.readyMany", { device, n: workers.length }) : t("engine.ready", { device });
    if (info.workers) again(30000);   // notice workers coming and going
  } else {
    engine.className = "status status-running engine-status";
    engine.textContent = t("engine.loading");
    engineTimer = setTimeout(async () => { await loadInfo(); showEngine(); }, 2000);
  }
}

async function loadInfo() {
  try {
    info = await api.info();
    document.getElementById("footer-version").textContent = `Netra Translate ${info.version}`;
    document.getElementById("footer-note").textContent = info.demo
      ? t("footer.demo", { h: info.limits.job_ttl_hours }) : t("footer.local");
  } catch {
    info = null;
  }
}

function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const hash = location.hash || "#/";
  const job = hash.match(/^#\/job\/([0-9a-f]{32})$/);
  document.querySelectorAll("[data-nav]").forEach((a) => a.removeAttribute("aria-current"));
  if (job) {
    document.querySelector('[data-nav="home"]').setAttribute("aria-current", "page");
    cleanup = renderJob(view, job[1], info);
  } else if (hash === "#/api") {
    document.querySelector('[data-nav="api"]').setAttribute("aria-current", "page");
    cleanup = renderApi(view, info);
  } else {
    document.querySelector('[data-nav="home"]').setAttribute("aria-current", "page");
    cleanup = renderHome(view, info);
  }
  window.scrollTo(0, 0);
}

window.addEventListener("netra:auth", () => {
  if (document.getElementById("auth-panel")) return;
  const input = h("input", { class: "input", type: "password", autocomplete: "off", "aria-label": "API key" });
  const save = async () => { setKey(input.value.trim()); await loadInfo(); showEngine(); route(); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
  const panel = h("section", { class: "wrap", id: "auth-panel" }, h("div", { class: "processing" },
    h("p", { class: "eyebrow muted2" }, "401"),
    h("h1", { class: "h2" }, t("auth.title")),
    h("p", { class: "note" }, t("auth.text")),
    h("p", { style: "margin-top:16px;max-width:24rem" }, input),
    h("p", { style: "margin-top:16px" },
      h("button", { class: "pill pill-primary", type: "button", onclick: save }, t("auth.save")))));
  if (cleanup) { cleanup(); cleanup = null; }
  view.replaceChildren(panel);
  input.focus();
});

window.addEventListener("hashchange", route);
applyStatic();
loadInfo().then(() => { showEngine(); route(); });
