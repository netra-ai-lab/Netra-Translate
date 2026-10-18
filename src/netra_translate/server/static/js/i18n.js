// UI strings. The interface is English; documents themselves are Khmer and
// English and render in Kantumruy Pro either way.
const STRINGS = {
  "nav.documents": "Documents",
  "nav.api": "API",
  "engine.loading": "Loading models…",
  "engine.ready": "Ready · {device}",
  "engine.readyMany": "Ready · {device} · {n} workers",
  "engine.noWorker": "Waiting for a worker…",
  "engine.offline": "Server unreachable",
  "footer.local": "Runs on this machine. Uploaded files never leave it.",
  "footer.demo": "Public demo. Files are deleted after {h} h; don't upload anything private.",
  "footer.apidocs": "API reference",
  "footer.licences": "Licences",
  "footer.issues": "Report a problem",

  "home.title": "Translate a document",
  "home.lede": "Khmer ↔ English for scans, photos and PDFs. The text is read with Netra OCR, translated with Netra MT, and exported to Word.",
  "home.demo": "<strong>This is a shared demo.</strong> Documents are listed only in this browser and deleted after {h} hours. Limit: {pages} pages, {mb} MB.",

  "drop.label": "Choose a PDF or image",
  "drop.title": "Drop a PDF or image here, or <span>browse</span>",
  "drop.meta": "PDF, JPG, PNG, TIFF, BMP, WebP · up to {mb} MB · {pages} pages · or paste an image",
  "drop.change": "Click to choose another file",
  "opt.direction": "Translate",
  "dir.auto": "Detect language",
  "dir.km2en": "Khmer → English",
  "dir.en2km": "English → Khmer",
  "opt.layout": "Detect structure",
  "opt.layoutDesc": "Headings, paragraphs, tables and figures. Slower; off gives one paragraph per text block.",
  "opt.layoutMissing": "Not installed on this server (netra-translate[layout]).",
  "opt.submit": "Translate",
  "opt.sending": "Uploading…",
  "opt.pick": "Choose a file first.",

  "recent.title": "Recent documents",
  "recent.note": "Kept for {h} hours, then deleted.",
  "recent.noteDemo": "Only documents uploaded in this browser. Kept for {h} hours.",
  "recent.empty": "No documents yet. Upload one above.",
  "col.name": "Document",
  "col.pages": "Pages",
  "col.status": "Status",
  "col.created": "Uploaded",
  "col.actions": "Actions",
  "recent.delete": "Delete document",
  "recent.confirm": "Delete?",
  "status.queued": "Waiting",
  "status.ocr": "Reading",
  "status.translate": "Translating",
  "status.done": "Ready",
  "status.error": "Failed",

  "proc.eyebrow.ocr": "Reading",
  "proc.eyebrow.translate": "Translating",
  "proc.page": "Reading page {done} of {total}",
  "proc.blocks": "Translating {done} of {total} blocks",
  "proc.queued": "Waiting for the previous document to finish",
  "proc.starting": "Starting…",
  "proc.note": "Time depends on the processor and how much text each page holds. You can leave this page; the document stays in Recent documents.",
  "proc.failed": "This document could not be translated.",
  "proc.retry": "Try again",
  "proc.reupload": "Upload again",
  "proc.back": "Back to documents",
  "proc.missing": "This document doesn't exist. It may have been deleted or expired.",

  "doc.original": "Original",
  "doc.translation": "Translation",
  "doc.showSource": "Show source text",
  "doc.direction": "Translation direction",
  "doc.copy": "Copy text",
  "doc.copied": "Translation copied",
  "doc.download": "Download Word",
  "doc.more": "More formats",
  "doc.bilingual": "Include the source text (bilingual)",
  "doc.page": "Page {n} of {total}",
  "doc.pageLabel": "Page {n}",
  "doc.prev": "Previous page",
  "doc.next": "Next page",
  "doc.empty": "No text was found in this document.",
  "doc.notTranslated": "Not translated",
  "fmt.docx": "Word document",
  "fmt.html": "Web page",
  "fmt.md": "Markdown",
  "fmt.json": "JSON — blocks + positions",
  "fmt.txt": "Plain text",

  "type.heading-1": "Heading 1",
  "type.heading-2": "Heading 2",
  "type.heading-3": "Heading 3",
  "type.paragraph": "Paragraph",
  "type.caption": "Caption",
  "type.page_header": "Page header",
  "type.page_footer": "Page footer",
  "type.table": "Table",
  "type.figure": "Figure",
  "type.formula": "Formula",

  "err.network": "Can't reach the server.",
  "err.generic": "Something went wrong.",
  "auth.title": "This server needs an API key",
  "auth.text": "Its operator set NETRA_API_KEY. Enter the key to continue.",
  "auth.save": "Save key",

  "api.title": "API",
  "api.lede": "Everything the app does is an HTTP endpoint. Anything that can send a file can use it; no SDK needed.",
  "api.s1": "Translate a file",
  "api.s1.text": "Upload returns a job. Poll it until status is done; a single image can also wait for the result.",
  "api.s2": "Export",
  "api.s2.text": "Download the translation as Word, HTML, Markdown, JSON or text. Add bilingual=true to keep the source next to each block.",
  "api.s3": "Change direction",
  "api.s3.text": "Translate the same document again without repeating OCR.",
  "api.s4": "Python",
  "api.s4.text": "Use the server with only requests, or run the models in your own process.",
  "api.s5": "Endpoints",
  "api.s5.text": "The full schema and a try-it console are at",
};

export function t(key, vars = {}) {
  const s = STRINGS[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`));
}

export function num(n) {
  return String(n);
}

export function applyStatic(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
}
