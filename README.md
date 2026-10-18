<div align="center">
  <img src="assets/symbol.svg" height="72" alt="Netra Lab" style="vertical-align: middle; margin-right: 24px;" />
  <img src="assets/wordmark-latin.svg" height="56" alt="Netra" style="vertical-align: middle;" />
</div>

<hr>

<p align="center">
  <a href="https://github.com/netra-ai-lab/Netra-Translate"><b>GitHub</b></a> |
  <a href="https://github.com/netra-ai-lab/Netra-Translate/pkgs/container/netra-translate"><b>Docker Image</b></a> |
  <a href="https://github.com/netra-ai-lab/Netra-OCR"><b>Netra-OCR</b></a> |
  <a href="https://github.com/netra-ai-lab/Netra-NMT"><b>Netra-NMT</b></a> |
  <a href="https://huggingface.co/Darayut"><b>Model Download</b></a>
</p>

<h2>
<p align="center">
  Netra Translate: Khmer ↔ English Document Translation
</p>
</h2>

<p align="center">
  Image or PDF in, translated document out. Runs on your own computer, on the CPU, offline.
</p>

## 1. Overview

Netra Translate puts two Netra Lab models behind one app. [Netra-OCR](https://github.com/netra-ai-lab/Netra-OCR) (17M parameters) reads the text off a scan, a phone photo or a PDF. [Netra-NMT](https://github.com/netra-ai-lab/Netra-NMT) (77M parameters) translates it between Khmer and English. You can use it as a web app in Docker, from the command line, from Python, or through a REST API.

```
image / PDF -> Netra-OCR (blocks) -> merge wrapped lines -> split sentences -> Netra-NMT -> DOCX / HTML / MD / TXT / JSON
```

Chaining the two models naively loses text. On top of the models, Netra Translate adds:

- **Line merging.** Without layout analysis, OCR returns one block per text line. The lines of a wrapped sentence are merged before translation.
- **Sentence splitting.** Netra-NMT truncates long input and can silently drop sentences, so each sentence is translated on its own (Khmer `។` and Latin `. ! ?`).
- **Direction detection.** Each block's direction comes from its script (Khmer or Latin). You can also force it.
- **Structure.** Headings, paragraphs, tables (cell by cell), and page headers and footers are kept. Figures pass through.
- **Bilingual output.** The source text can sit next to each translation.

## 2. Quick start

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) for Windows, Mac or Linux. In its settings, give it at least 4 GB of memory.
2. Open a terminal (PowerShell on Windows, Terminal on Mac) and run:

   ```bash
   docker run -d --name netra-translate -p 8000:8000 -v netra-data:/data ghcr.io/netra-ai-lab/netra-translate
   ```

3. Open http://localhost:8000. The header shows "Ready · CPU" once the models have loaded.

After the first run, the app appears in Docker Desktop's *Containers* list, where you can start and stop it without a terminal. The `-v netra-data:/data` part keeps your recent documents when the container restarts. Without it, they are lost on restart.

> **The page won't open?** The app needs port 8000, which `-p 8000:8000` sets up. If you start the image from Docker Desktop's *Images* tab instead, open *Optional settings* and set *Host port* to `8000`.

To update to a new version:

```bash
docker pull ghcr.io/netra-ai-lab/netra-translate
docker rm -f netra-translate
docker run -d --name netra-translate -p 8000:8000 -v netra-data:/data ghcr.io/netra-ai-lab/netra-translate
```

| | |
| :--- | :--- |
| Platforms | Windows and Linux PCs (x86-64) and ARM64, including Apple Silicon Macs |
| GPU | Not needed; runs on the CPU |
| Download | About 760 MB (2.5 GB unpacked), all models included |
| Memory | About 1 GB while translating a one-page scan |
| Internet | Not needed after the download. Files never leave your computer. |
| Input | PDF (up to 100 pages), JPG, PNG, TIFF, BMP or WebP, up to 50 MB |
| Output | Translated pages as PDF or PNG; text as Word (.docx), HTML, Markdown, plain text or JSON; translation only or bilingual |

`docker compose up` with the included [docker-compose.yml](docker-compose.yml) does the same, and lists the settings you can change.

## 3. Install with pip

For developers. Netra Translate isn't on PyPI yet, because it depends on netra-nmt from GitHub and PyPI doesn't accept git dependencies.

```bash
pip install "netra-translate[all] @ git+https://github.com/netra-ai-lab/Netra-Translate.git"
# or, from a checkout:  pip install -e ".[all]"
```

| Extra | Adds |
| --- | --- |
| *(none)* | The library and the `netra-translate translate` command |
| `server` | The web app and REST API (`netra-translate serve`) |
| `layout` | Layout analysis: headings, paragraphs, tables and reading order |
| `client` | The Python client for a running server (`netra_translate.Client`) |
| `all` | `server` + `layout` + `client` |

The first run downloads model weights from Hugging Face: about 180 MB for NMT, plus the OCR models. The CPU is enough; CUDA is used when available. To download them ahead of time, for example on a machine that will later run offline:

```bash
netra-translate download            # OCR recognizer + translator (--layout adds the layout model)
HF_HUB_OFFLINE=1 netra-translate translate -i scan.jpg
```

Weights go to the Hugging Face cache (`HF_HOME`, default `~/.cache/huggingface`). The text-line detector and the tokenizer ship inside their packages.

> **netra-nmt must come from GitHub**, not PyPI. The PyPI release `netra-nmt` 0.1.0 has an older architecture than the published weights and produces garbage. No error is raised, because the weights load with `strict=False`. `pyproject.toml` already points at GitHub.

## 4. Usage

**Web app.** Upload a document, then read the original and the translated page side by side. [More](docs/web-app.md)

```bash
netra-translate serve --open        # http://127.0.0.1:8000
```

**Command line.** One file or a whole folder; the models load once per batch. [All options](docs/cli.md)

```bash
netra-translate translate -i scan.jpg                            # print the translation
netra-translate translate -i letter.pdf -o letter.docx --layout  # the extension picks the format
netra-translate translate -i scans/ --save_path output/ -f md --bilingual
```

**Python.** [Full API](docs/python.md)

```python
from netra_translate import NetraTranslate

pipeline = NetraTranslate(direction="auto")       # models load on first use, once
for res in pipeline.predict("letter.pdf"):
    res.print()                                   # translated text
    res.save_to_docx("output/")                   # output/letter_translated.docx
```

**REST API.** Upload, poll, download. [Endpoints](docs/rest-api.md)

```bash
curl -F file=@letter.pdf -F direction=km2en http://localhost:8000/v1/translate   # -> 202 {"job": {...}}
curl http://localhost:8000/v1/jobs/<id>                                          # until "status": "done"
curl -o letter.docx "http://localhost:8000/v1/jobs/<id>/export?format=docx"
```

| Reference | |
| --- | --- |
| [Configuration](docs/configuration.md) | Environment variables, config files, API keys |
| [Scaling](docs/scaling.md) | Several workers on one queue, readiness checks |
| [Migrating from netra-ocr-mt](docs/migrating.md) | Old names and their replacements |
| [Development](docs/development.md) | Tests, releasing, building the image |

## 5. Limitations

- Translation quality and OCR accuracy are those of the upstream models. Netra-OCR is Khmer-first, so English text can come back with small errors (a dropped space or period), which then flow into the translation.
- Line merging is a heuristic: the previous line is unfinished, the vertical gap is small and the lines overlap horizontally. Multi-column pages without layout analysis can merge wrongly; use `--layout` or `--no-merge`.
- Netra-NMT works sentence by sentence, with a 256-token input limit. Over-long sentences are split at clause punctuation or a hard length cap.
- Without `NETRA_API_KEY`, anyone who can reach the port can use the server. Set the key, or put the server behind a proxy, before exposing it beyond your machine.

## 6. Licensing

This project is MIT, and so are Netra-OCR and Netra-NMT. However, Netra-OCR's YOLO and layout extras pull in `ultralytics` and `doclayout-yolo`, which are **AGPL-3.0**. The Docker image contains both, so it is labelled `MIT AND AGPL-3.0-only`. Check the upstream [`THIRD_PARTY_LICENSES.md`](https://github.com/netra-ai-lab/Netra-OCR/blob/master/THIRD_PARTY_LICENSES.md) before redistributing, or before running a modified public service. Part of the OCR recognizer's training data is licensed for non-commercial use only, so don't treat the app as cleared for commercial use. The bundled Kantumruy Pro font is under the SIL Open Font License (`src/netra_translate/server/static/fonts/OFL.txt`).
