---
title: Netra Translate 1
emoji: 📄
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: Translate Khmer and English scans and PDFs
---

# Netra Translate 1

Drop in a scan, a phone photo or a PDF. Netra Translate reads the text with
[Netra-OCR](https://github.com/netra-ai-lab/Netra-OCR), translates it between Khmer and English with
[Netra-NMT](https://github.com/netra-ai-lab/Netra-NMT), and lets you export a Word file, Markdown,
HTML, text or JSON, with or without the source text.

This demo runs on a shared server and is limited to 5 pages and 10 MB per file.
For private documents, run the app on your own computer:

```bash
docker run -d --name netra-translate -p 8000:8000 ghcr.io/netra-ai-lab/netra-translate
```

Then open http://localhost:8000. It runs on the CPU and needs no internet after the download.
Source and install instructions: https://github.com/netra-ai-lab/Netra-Translate
