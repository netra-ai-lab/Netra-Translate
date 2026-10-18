[← Netra Translate](../README.md)

# Web app

```bash
netra-translate serve --open        # http://127.0.0.1:8000   (--host, --port, --data-dir, --config)
```

The app follows the [Netra OCR](https://github.com/netra-ai-lab/Netra-OCR) app and the Netra Lab brand. It has three screens:

- **Documents.** Drop, browse for or paste a scan or PDF, pick the languages, and press *Translate*. Recent documents are shown below as cards with their progress. They are deleted after 24 hours.
- **Document view.** The original page is on the left. On the right is a clean copy of the same page in the other language: every line sits where it was in the scan, at the same size and in the same colour, with tables and figures in place. Hovering a line highlights the same line on both pages. You can view the pages side by side, or only the original or only the translation, and zoom. Changing the direction translates again without repeating OCR. *Download* saves the translated pages as a PDF or a PNG, or the text as Word, HTML, Markdown, text or JSON, optionally bilingual.
- **API.** Copy-paste examples for the REST API, using this server's address.

Jobs are stored on disk and run by a worker inside the server, one at a time; see [Scaling](scaling.md) to run several. Reloading the page, or restarting the server, does not lose a document: finished ones stay, and queued ones run when the server is back. The page needs no build step: plain HTML, CSS and JavaScript modules, with the Kantumruy Pro font bundled so it works offline.
