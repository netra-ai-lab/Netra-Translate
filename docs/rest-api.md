[← Netra Translate](../README.md)

# REST API

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
