# Netra Translate 1

Image or PDF in, translated document out (Khmer ↔ English). Built on two Netra Lab models:
[Netra-OCR](https://github.com/netra-ai-lab/Netra-OCR) reads the text and [Netra-NMT](https://github.com/netra-ai-lab/Netra-NMT) translates it.
Use it as an app on your own computer (Docker), from the command line, from Python, or as a REST API.

```
image / PDF -> Netra-OCR (blocks) -> merge wrapped lines -> split sentences -> Netra-NMT -> DOCX / HTML / MD / TXT / JSON
```

On top of the two models, Netra Translate adds:

- **Line merging.** Without layout analysis, OCR returns one block per text line. The lines of a wrapped sentence are merged before translation.
- **Sentence splitting.** Netra-NMT truncates long input and can silently drop sentences, so each sentence is translated on its own (Khmer `។` and Latin `. ! ?`).
- **Direction detection** per block, from the script (Khmer or Latin). It can also be forced.
- **Structure kept.** Headings, paragraphs, tables (cell by cell) and page headers and footers are kept. Figures pass through.
- **Bilingual output,** with the source text next to each translation.

**Contents:** [Quick start](#quick-start) · [Web app](#web-app) · [Command line](#command-line) · [Python API](#python-api) · [REST API](#rest-api) · [Configuration](#configuration) · [Migrating from netra-ocr-mt](#migrating-from-netra-ocr-mt) · [Limitations](#limitations) · [Licensing](#licensing)

## Quick start

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
| Output | Word (.docx), HTML, Markdown, plain text or JSON; translation only or bilingual |

`docker compose up` with the included [docker-compose.yml](docker-compose.yml) does the same, and lists the settings you can change.

**Try it online.** A public demo runs on Hugging Face Spaces, limited to 5 pages and 10 MB per file, and files are deleted after an hour. It is a shared server, so use the Docker app for private documents.

**Install with pip (for developers).** Netra Translate isn't on PyPI yet, because it depends on netra-nmt from GitHub and PyPI doesn't accept git dependencies.

```bash
pip install "netra-translate[all] @ git+https://github.com/netra-ai-lab/netra-translate.git"
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

## Web app

```bash
netra-translate serve --open        # http://127.0.0.1:8000   (--host, --port, --data-dir, --config)
```

The app follows the [Netra OCR](https://github.com/netra-ai-lab/Netra-OCR) app and the Netra Lab brand. It has three screens:

- **Documents.** Drop, browse for or paste a scan or PDF, choose the direction, and press *Translate*. Recent documents are listed below with their progress. They are deleted after 24 hours.
- **Document view.** The original page is on the left, with a box around each block. The translation is on the right, with the source text under each block. Hovering a block highlights its box, and clicking a box jumps to its block. Changing the direction translates again without repeating OCR. *Download Word* is one click away; *More formats* offers Markdown, HTML, text and JSON, optionally bilingual.
- **API.** Copy-paste examples for the REST API, using this server's address.

Jobs are stored on disk and run by a worker inside the server, one at a time; see [Scaling](#scaling) to run several. Reloading the page, or restarting the server, does not lose a document: finished ones stay, and queued ones run when the server is back. The page needs no build step: plain HTML, CSS and JavaScript modules, with the Kantumruy Pro font bundled so it works offline.

## Command line

```bash
netra-translate translate -i scan.jpg                            # print the translation
netra-translate translate -i scan.jpg --save_path output/        # output/scan_translated.docx
netra-translate translate -i letter.pdf --save_path output/ -f md --bilingual
netra-translate translate -i letter.pdf -o letter.docx --layout  # the extension picks the format
netra-translate translate -i scan.jpg -d km2en --mode beam --beam 5
netra-translate translate -i scans/ "more/*.pdf" --save_path output/   # many files, one result each
netra-translate translate -i scan.jpg --config netra.yaml
netra-translate download [--layout]
netra-translate serve --port 8000
netra-translate worker                                           # see Scaling
netra-translate version
```

| Option | Meaning |
| --- | --- |
| `-i`, `--input` | Images (JPG, PNG, TIFF, BMP, WebP) or PDFs; also directories and globs |
| `--save_path DIR` | Write to a directory, named after each input; `-f` picks the format (default `docx`) |
| `-c`, `--config` | A YAML or JSON file of pipeline options ([example](examples/config.yaml)); flags override it |
| `-o FILE` | Write to a file; the extension picks the format (`.docx .html .md .txt .json`) |
| `-d`, `--direction` | `auto` (default; per block), `km2en` or `en2km` |
| `--bilingual` | Put the source next to each translated block |
| `--layout` | Layout analysis (needs the `layout` extra) |
| `--no-merge` | Don't merge OCR lines into paragraphs before translating |
| `--max-pages`, `--device`, `--detector`, `--mode`, `--beam`, `--ocr-beam` | Advanced |

`python -m netra_translate …` works the same way. With several inputs, `--save_path` is required. Each file prints a status line, a file that fails is reported and skipped, and the exit code is 1 if any failed. The models load once for the whole batch.

## Python API

```python
from netra_translate import NetraTranslate

pipeline = NetraTranslate(direction="auto")       # models load on first use, once
for res in pipeline.predict("letter.pdf"):        # a path, bytes, or a list of them
    res.print()                                   # translated text
    res.save_to_docx("output/")                   # output/letter_translated.docx
    res.save_to_markdown("output/", bilingual=True)
    res.save_to_json("output/")

data = res.json                                   # the translated document as a dict
for block in res.translated.blocks:
    print(block["type"], block.get("source_text"), "->", block.get("text"))
```

| | |
| --- | --- |
| `NetraTranslate(direction, layout, detector, device, mode, beam_size, merge_lines)` | The pipeline |
| `NetraTranslate.from_config("netra.yaml", **overrides)` | The same, from a config file |
| `.predict(input)` / `.predict_iter(input)` | List of `TranslationResult`, or a generator over them for many files |
| `res.print(bilingual=False)`, `res.text`, `res.json` | Read the result |
| `res.save_to_docx / save_to_markdown / save_to_json(path)` | `path` is a directory (the file is named after the input) or a file path |
| `res.save(path)`, `res.export(fmt)` | Any format, or `(bytes, filename, mimetype)` |

The JSON is Netra-OCR's document schema. Translated text blocks add `source_text` and `direction`, and tables add `source_rows`. More in [examples/](examples/).

**Client for a running server** (the `client` extra):

```python
from netra_translate import Client

with Client("http://localhost:8000", api_key=None) as client:
    out = client.translate("letter.pdf", direction="km2en")   # uploads, waits, returns {"job", "result"}
    open("letter.docx", "wb").write(client.export(out["job"]["id"], "docx"))
```

`Client` also has `submit`, `job`, `wait`, `result`, `retranslate`, `delete`, `jobs`, `info` and `ready`. Errors raise `NetraAPIError` with the HTTP status and the server's message.

## REST API

```bash
netra-translate serve                                   # or: uvicorn netra_translate.server.app:app
curl -F file=@letter.pdf -F direction=km2en http://localhost:8000/v1/translate   # -> 202 {"job": {...}}
curl http://localhost:8000/v1/jobs/<id>                 # poll until "status": "done"
curl -o letter.docx "http://localhost:8000/v1/jobs/<id>/export?format=docx"
curl -F file=@scan.jpg -F wait=true http://localhost:8000/v1/translate           # one image: wait for the result
```

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/translate` | Upload a file (multipart `file`; `direction`, `layout`, `wait`). Returns 202 and a job. |
| `GET /v1/jobs/{id}` | Status (`queued`, `running`, `done`, `error`) and progress (`ocr` pages, then `translate` blocks) |
| `GET /v1/jobs/{id}/result` | The translated document |
| `POST /v1/jobs/{id}/translate?direction=` | Translate again in another direction, without repeating OCR |
| `GET /v1/jobs/{id}/export?format=&bilingual=` | Download `docx`, `html`, `md`, `txt` or `json` |
| `GET /v1/jobs/{id}/assets/{asset}` | Page images and figure crops |
| `GET /v1/jobs`, `DELETE /v1/jobs/{id}` | List recent jobs, delete one |
| `GET /v1/info` | Version, device, limits, and the live workers |
| `GET /health` | Liveness: the API is up (`models_ready` says whether a worker has loaded its models) |
| `GET /ready` | Readiness: 200 once a worker has its models loaded, 503 until then (for load balancers) |

Interactive API docs are at `/docs` in the running app. Each worker processes one job at a time, in upload order. Uploads are deleted once OCR is done, and everything else is deleted after `NETRA_JOB_TTL_HOURS`.

## Configuration

The server reads these environment variables. In Docker, pass them with `-e`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `NETRA_HOST`, `NETRA_PORT` | `127.0.0.1`, `8000` | Where `netra-translate serve` listens (the Docker image uses `0.0.0.0`) |
| `NETRA_DATA_DIR` | `~/.cache/netra-translate/jobs` (`/data` in Docker) | Where jobs are stored |
| `NETRA_JOB_TTL_HOURS` | `24` | Delete documents this long after their last change |
| `NETRA_MAX_UPLOAD_MB`, `NETRA_MAX_PAGES` | `50`, `100` | Upload limits |
| `NETRA_API_KEY` | none | Require `X-API-Key` (or `Authorization: Bearer`) on `/v1/*` |
| `NETRA_LAYOUT` | `0` | Layout analysis on by default |
| `NETRA_DEVICE`, `NETRA_DETECTOR` | auto, `yolo` | Model device and text-line detector |
| `NETRA_WARMUP` | `1` | Load the models at start-up, so the first upload isn't slow |
| `NETRA_SYNC_TIMEOUT` | `120` | Seconds `wait=true` waits before answering 202 |
| `NETRA_DEMO` | `0` | Shared public server: never list jobs, and show a demo notice (used by the Hugging Face Space) |
| `NETRA_EMBEDDED_WORKER` | `1` | Run a worker inside `serve`; `0` is the same as `serve --no-worker` |
| `NETRA_THREADS` | `0` (all cores) | torch CPU threads per worker |

`serve` and `worker` also take `--config FILE`: the `server:` section of a YAML or JSON file sets these options by their lower-case names (`max_pages`, `job_ttl_hours`, …; see [examples/config.yaml](examples/config.yaml)). Order of precedence: flags, then the file, then the environment, then the defaults. An unknown option is an error.

Without `NETRA_API_KEY`, anyone who can reach the port can use the server. Set the key, or put the server behind a proxy, before exposing it beyond your machine.

## Scaling

By default `netra-translate serve` is one process: the API plus one worker that runs jobs one at a time. To run several jobs at once, start the API without a worker and add worker processes on the same data directory:

```bash
netra-translate serve --no-worker --data-dir /srv/netra
netra-translate worker --data-dir /srv/netra --threads 2      # start as many as fit
netra-translate worker --data-dir /srv/netra --threads 2
```

With Docker Compose:

```bash
docker compose -f docker-compose.yml -f docker-compose.scale.yml up --build --scale worker=3
```

- **The data directory is the queue.** Uploads are queued as files, and a worker claims one with an atomic rename, so a job runs only once whichever worker is free. The order is upload order. The directory must be a local disk or a volume where rename is atomic; a network share that doesn't guarantee that isn't supported.
- **Each worker loads its own models**, so memory grows with every worker. The API process loads none. Measured on native Windows (CPU, one-page scan, no layout model): API process 317 MB; each worker about 0.83 GB, peaking at 0.98 GB during a job. Set `--threads` (`NETRA_THREADS`) so that workers × threads doesn't exceed the CPU cores.
- **Workers come and go.** A worker writes a heartbeat every 5 seconds. One that stops for 30 seconds is considered gone, and its job is marked failed with a message to retry. `SIGTERM` (or Ctrl+C) lets the worker finish its current job first; a second one stops it at once. Jobs still queued wait for the next worker, and survive restarts.
- **`GET /ready`** returns 503 until a worker has loaded its models; use it as a load-balancer or Kubernetes readiness check. The nav bar shows the number of workers, and *Waiting for a worker…* when there are none.
- Give workers the same `NETRA_MAX_PAGES` as the API. On a worker, `NETRA_LAYOUT=1` only means it loads the layout model at start-up; each job carries its own layout choice.

## Migrating from netra-ocr-mt

The preview releases were called `netra-ocr-mt`. The old names still work in 1.0, with a deprecation warning, and will be removed in the next release.

| Before | Now |
| --- | --- |
| `pip install netra-ocr-mt[server]` | `pip install netra-translate[server]` (or `[all]`) |
| `from netra_ocr_mt import OCRTranslator` | `from netra_translate import NetraTranslate` |
| `OCRTranslator().run(path)` | `NetraTranslate().predict(path)` (`run` still works) |
| `ocr-translate scan.jpg -o out.docx` | `netra-translate translate -i scan.jpg -o out.docx` |
| `ocr-translate-web` | `netra-translate serve` |
| `POST /v1/ocr-translate` | `POST /v1/translate`, then `GET /v1/jobs/{id}/export` |
| `/v1/results/{id}/…` | `/v1/jobs/{id}/…` |
| `NETRA_MAX_RESULTS` | `NETRA_JOB_TTL_HOURS` (jobs are stored on disk) |

## Limitations

- Translation quality and OCR accuracy are those of the upstream models. Netra-OCR is Khmer-first, so English text can come back with small errors (a dropped space or period), which then flow into the translation.
- Line merging is a heuristic: the previous line is unfinished, the vertical gap is small and the lines overlap horizontally. Multi-column pages without layout analysis can merge wrongly; use `--layout` or `--no-merge`.
- Netra-NMT works sentence by sentence, with a 256-token input limit. Over-long sentences are split at clause punctuation or a hard length cap.
- The translation is not drawn back onto the image.

## Licensing

This project is MIT, and so are Netra-OCR and Netra-NMT. However, Netra-OCR's YOLO and layout extras pull in `ultralytics` and `doclayout-yolo`, which are **AGPL-3.0**. The Docker image contains both, so it is labelled `MIT AND AGPL-3.0-only`. Check the upstream [`THIRD_PARTY_LICENSES.md`](https://github.com/netra-ai-lab/Netra-OCR/blob/master/THIRD_PARTY_LICENSES.md) before redistributing, or before running a modified public service. Part of the OCR recognizer's training data is licensed for non-commercial use only, so don't treat the app as cleared for commercial use. The bundled Kantumruy Pro font is under the SIL Open Font License (`src/netra_translate/server/static/fonts/OFL.txt`).

## Releasing

Push a version tag (`git tag v1.0.0 && git push --tags`). [`.github/workflows/docker.yml`](.github/workflows/docker.yml) then builds amd64 and arm64 images natively, runs the smoke test on both, and publishes `ghcr.io/netra-ai-lab/netra-translate:1.0.0`, `:1.0` and `:latest`. After that, bump the tag in [`hf-space/Dockerfile`](hf-space/Dockerfile) and push that folder to the Space.

To build the image yourself, run `docker build -f docker/Dockerfile -t netra-translate .`. The build downloads every model and runs [a smoke test](docker/smoke_test.py) against the real models.

## Tests

```bash
pip install -e ".[server,dev]" && pytest      # the unit tests use fake models, so no weights are needed
```
