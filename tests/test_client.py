"""netra_translate.Client against the real app (FastAPI's TestClient is an httpx.Client)."""
import io

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")
pytest.importorskip("httpx")
from conftest import FakeOCR, FakeTranslator
from fastapi.testclient import TestClient
from PIL import Image

from netra_translate import Client, NetraTranslate
from netra_translate.client import NetraAPIError
from netra_translate.server.app import create_app
from netra_translate.server.settings import Settings


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def make(tmp_path, sample_blocks):
    opened = []

    def make(ocr=None, api_key=None, **kw):
        settings = Settings(data_dir=str(tmp_path / "jobs"), warmup=False, api_key=api_key, demo=False, **kw)
        factory = lambda layout: NetraTranslate(ocr=ocr or FakeOCR(sample_blocks), translator=FakeTranslator())
        http = TestClient(create_app(settings, pipeline_factory=factory))
        http.__enter__()
        opened.append(http)
        return http

    yield make
    for http in opened:
        http.__exit__(None, None, None)


def test_translate_and_export(make, tmp_path):
    scan = tmp_path / "letter.png"
    scan.write_bytes(png())
    client = Client(http=make())
    assert client.ready() and client.info()["name"] == "Netra Translate"

    out = client.translate(scan, direction="km2en")
    job = out["job"]
    assert job["status"] == "done" and job["filename"] == "letter"
    assert out["result"]["blocks"][1]["text"] == "[km2en] The weather is nice today."
    assert client.export(job["id"], "docx")[:2] == b"PK"
    assert "[km2en] The weather" in client.export(job["id"], "txt", bilingual=True).decode("utf-8")
    assert [j["id"] for j in client.jobs()] == [job["id"]]

    again = client.retranslate(job["id"], "en2km")
    assert again["status"] == "done" and again["direction"] == "en2km"

    client.delete(job["id"])
    with pytest.raises(NetraAPIError) as e:
        client.job(job["id"])
    assert e.value.status == 404 and "not found" in e.value.detail


def test_bytes_and_no_wait(make):
    client = Client(http=make())
    job = client.translate(png(), filename="scan.png", wait=False)["job"]
    assert job["status"] in ("queued", "running", "done")
    assert client.wait(job["id"], timeout=10)["status"] == "done"


def test_errors_are_raised(make):
    class Broken(FakeOCR):
        def process_document(self, source, **kw):
            raise ValueError("bad image")

    client = Client(http=make(ocr=Broken([])))
    with pytest.raises(NetraAPIError) as e:
        client.translate(png())
    assert "bad image" in e.value.detail and e.value.job["status"] == "error"
    with pytest.raises(NetraAPIError) as e:
        client.translate(b"not an image")
    assert e.value.status == 415


def test_api_key(make):
    http = make(api_key="s3cret")
    with pytest.raises(NetraAPIError) as e:
        Client(http=http).info()
    assert e.value.status == 401
    assert Client(http=http, api_key="s3cret").info()["auth"] is True


def test_lazy_export():
    import netra_translate
    assert netra_translate.Client is Client
    with pytest.raises(AttributeError):
        netra_translate.Nope
