"""Build-time check that the (pruned) image still runs everything the app does.

The Dockerfile uninstalls packages that the dependencies declare but inference never
imports. This exercises every path the server can reach -- OCR with and without
layout analysis, image and PDF input, both translation directions, every export
format, and a job through the REST API with the real models -- so a prune that goes
too far fails the build instead of the first upload.
"""

import io
import tempfile

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from netra_translate import FORMATS, NetraTranslate, Translator
from netra_translate.server.app import create_app
from netra_translate.server.settings import Settings

page = np.full((900, 700, 3), 255, np.uint8)
cv2.putText(page, "Annual Report", (200, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
for i, y in enumerate(range(170, 600, 45)):
    cv2.putText(page, f"The weather is nice today. Line {i + 1}.", (60, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
png = cv2.imencode(".png", page)[1].tobytes()
pdf = io.BytesIO()
Image.fromarray(page).save(pdf, "PDF")

translator = Translator(device="cpu")
for text, direction in [("The weather is nice today.", "en2km"),
                        ("ថ្ងៃនេះអាកាសធាតុល្អ។", "km2en")]:
    out, used = translator.translate(text, "auto")
    assert used == direction, (text, used)
    assert out.strip() and out != text, (text, out)
    print(f"{direction}: {text!r} -> {out!r}")

for layout, source in [(False, png), (True, png), (True, pdf.getvalue())]:
    pipe = NetraTranslate(layout=layout, device="cpu", translator=translator)
    [result] = pipe.predict(source)
    blocks = [b for b in result.translated.blocks if b.get("text")]
    assert blocks, f"layout={layout}: no text blocks"
    print(f"layout={layout!s:5s} -> {len(blocks)} translated blocks")

for fmt in FORMATS:
    for bilingual in (False, True):
        data, name, _ = result.export(fmt, bilingual=bilingual)
        assert data, fmt
    print(f"export {fmt}: {len(data)} bytes")

# The server: upload -> worker -> result -> export, with the real models.
with tempfile.TemporaryDirectory() as data_dir:
    settings = Settings(data_dir=data_dir, warmup=False, device="cpu", demo=False, api_key=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        r = client.post("/v1/translate", files={"file": ("page.pdf", pdf.getvalue(), "application/pdf")},
                        data={"direction": "en2km"})
        assert r.status_code == 202, r.text
        job = client.app.state.jobs.wait(r.json()["job"]["id"], 600)
        assert job.status == "done", job.error
        assert client.get(f"/v1/jobs/{job.id}/result").json()["blocks"]
        image = client.get(f"/v1/jobs/{job.id}/assets/page-0")
        assert image.status_code == 200, "page image not stored"
        for fmt in FORMATS:
            r = client.get(f"/v1/jobs/{job.id}/export", params={"format": fmt})
            assert r.status_code == 200 and r.content, fmt
        print("server job: done, every format exported")

# Scaled mode: an API with --no-worker and a separate worker on the same data dir.
from netra_translate.server.jobs import JobStore  # noqa: E402
from netra_translate.server.worker import Worker  # noqa: E402

with tempfile.TemporaryDirectory() as data_dir:
    settings = Settings(data_dir=data_dir, warmup=False, device="cpu", demo=False, api_key=None,
                        embedded_worker=False, sync_timeout=600)
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").status_code == 503
        worker = Worker(settings, JobStore(settings),
                        lambda layout: NetraTranslate(layout=layout, device="cpu", translator=translator))
        worker.start()
        try:
            assert client.get("/ready").status_code == 200
            r = client.post("/v1/translate", files={"file": ("page.png", png, "image/png")},
                            data={"direction": "en2km", "wait": "true"})
            assert r.status_code == 200 and r.json()["job"]["status"] == "done", r.text
        finally:
            worker.stop(timeout=60)
        print("separate worker: done")

print("smoke test passed")
