import { t } from "./i18n.js";
import { h } from "./util.js";

function section(n, title, text, ...content) {
  return h("section", { class: "rail" },
    h("div", {}, h("div", { class: "rail-label eyebrow" },
      h("span", { class: "num" }, String(n).padStart(2, "0")), h("span", { class: "slash" }, "/"),
      h("span", { class: "muted2" }, title))),
    h("div", { class: "prose" }, h("p", { class: "body-text muted" }, text), ...content));
}

function code(text) {
  return h("pre", { class: "code" }, h("code", {}, text));
}

export function renderApi(root, info) {
  const origin = location.origin;
  const key = info?.auth ? ' -H "X-API-Key: $NETRA_API_KEY"' : "";
  const pyAuth = info?.auth ? ", headers=H" : "";

  const endpoints = [
    ["POST", "/v1/translate", "Upload a PDF or image (multipart file, direction, layout, wait)."],
    ["GET", "/v1/jobs/{id}", "Status and progress (phase ocr → translate)."],
    ["GET", "/v1/jobs/{id}/result", "The translated document: pages + blocks, each with source_text."],
    ["POST", "/v1/jobs/{id}/translate?direction=", "Translate again in another direction; OCR is not repeated."],
    ["GET", "/v1/jobs/{id}/export?format=docx", "docx · html · md · txt · json, optional &bilingual=true"],
    ["GET", "/v1/jobs/{id}/assets/{asset}", "Page renders and figure crops."],
    ["DELETE", "/v1/jobs/{id}", "Delete the job and its files."],
    ["GET", "/v1/jobs", info?.demo ? "Recent jobs (always empty on this demo server)." : "Recent jobs, newest first."],
    ["GET", "/v1/info", "Version, device, directions, formats and limits."],
    ["GET", "/health", "Liveness, plus whether the models have loaded."],
  ];

  root.replaceChildren(h("div", { class: "wrap" },
    h("section", { class: "page page-head api-head" },
      h("h1", { class: "h2" }, t("api.title")),
      h("p", { class: "meta" }, t("api.lede"))),
    section(1, t("api.s1"), t("api.s1.text"),
      code(`# Returns 202 and a job; poll it until "status" is "done"
curl${key} -F file=@letter.pdf -F direction=km2en ${origin}/v1/translate
curl${key} ${origin}/v1/jobs/<id>
curl${key} ${origin}/v1/jobs/<id>/result

# A single image can wait for the finished result instead
curl${key} -F file=@scan.jpg -F wait=true ${origin}/v1/translate`)),
    section(2, t("api.s2"), t("api.s2.text"),
      code(`curl${key} -o letter.docx "${origin}/v1/jobs/<id>/export?format=docx"
curl${key} -o letter.md "${origin}/v1/jobs/<id>/export?format=md&bilingual=true"`)),
    section(3, t("api.s3"), t("api.s3.text"),
      code(`curl${key} -X POST "${origin}/v1/jobs/<id>/translate?direction=en2km"`)),
    section(4, t("api.s4"), t("api.s4.text"),
      code(`import time, requests

URL = "${origin}"${info?.auth ? '\nH = {"X-API-Key": "..."}' : ""}

with open("letter.pdf", "rb") as f:
    job = requests.post(f"{URL}/v1/translate", files={"file": f},
                        data={"direction": "km2en"}${pyAuth}).json()["job"]

while job["status"] not in ("done", "error"):
    time.sleep(1)
    job = requests.get(f"{URL}/v1/jobs/{job['id']}"${pyAuth}).json()["job"]

docx = requests.get(f"{URL}/v1/jobs/{job['id']}/export", params={"format": "docx"}${pyAuth})
open("letter_translated.docx", "wb").write(docx.content)`),
      code(`# Or without a server: pip install "netra-translate @ git+https://github.com/netra-ai-lab/netra-translate"
from netra_translate import NetraTranslate

pipeline = NetraTranslate(direction="km2en")
for res in pipeline.predict("letter.pdf"):
    res.print()
    res.save_to_docx("output/")`)),
    section(5, t("api.s5"), t("api.s5.text"),
      h("p", {}, h("a", { href: "/docs", target: "_blank", rel: "noopener" }, `${origin}/docs`)),
      h("div", {}, endpoints.map(([verb, path, desc]) => h("div", { class: "endpoint" },
        h("span", { class: "verb" }, verb),
        h("div", {}, h("code", {}, path), h("p", { class: "meta muted", style: "margin-top:6px" }, desc))))))));
  return null;
}
