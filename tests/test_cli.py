import json
import os

import pytest
from conftest import FakeOCR, FakeTranslator

from netra_translate import NetraTranslate, __version__, cli


@pytest.fixture
def fake_pipeline(monkeypatch, sample_blocks):
    """Make the CLI build a NetraTranslate backed by fake models; returns the kwargs it got."""
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return NetraTranslate(ocr=FakeOCR(sample_blocks), translator=FakeTranslator(),
                              direction=kw.get("direction", "auto"))

    def from_config(path, **overrides):
        from netra_translate.config import load_config
        return factory(**{**load_config(path, "pipeline", NetraTranslate.CONFIG_KEYS), **overrides})

    factory.from_config = from_config
    monkeypatch.setattr("netra_translate.pipeline.NetraTranslate", factory)
    return seen


@pytest.fixture
def scan(tmp_path):
    p = tmp_path / "scan.png"
    p.write_bytes(b"\x89PNG fake")
    return p


def test_version(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == f"netra-translate {__version__}"


def test_subcommand_required(capsys):
    with pytest.raises(SystemExit):
        cli.main([])


def test_translate_prints_text(fake_pipeline, scan, capsys):
    assert cli.main(["translate", "-i", str(scan)]) == 0
    assert "[en2km] The weather is nice today." in capsys.readouterr().out


def test_translate_positional_input_and_direction(fake_pipeline, scan, capsys):
    assert cli.main(["translate", str(scan), "-d", "km2en"]) == 0
    assert fake_pipeline["direction"] == "km2en"
    assert "[km2en] Annual Report" in capsys.readouterr().out


def test_save_path_names_file_after_input(fake_pipeline, scan, tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main(["translate", "-i", str(scan), "--save_path", str(out)]) == 0
    assert (out / "scan_translated.docx").read_bytes()[:2] == b"PK"
    assert cli.main(["translate", "-i", str(scan), "--save-path", str(out), "-f", "json"]) == 0
    data = json.loads((out / "scan_translated.json").read_text(encoding="utf-8"))
    assert data["blocks"][1]["source_text"] == "The weather is nice today."


def test_output_file(fake_pipeline, scan, tmp_path):
    target = tmp_path / "result.md"
    assert cli.main(["translate", "-i", str(scan), "-o", str(target), "--bilingual"]) == 0
    text = target.read_text(encoding="utf-8")
    assert "The weather is nice today." in text and "[en2km] The weather is nice today." in text


def test_missing_input(fake_pipeline, tmp_path, capsys):
    assert cli.main(["translate"]) == 2
    assert cli.main(["translate", "-i", str(tmp_path / "nope.png")]) == 2


def test_save_path_and_output_are_exclusive(fake_pipeline, scan, tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["translate", "-i", str(scan), "--save_path", str(tmp_path), "-o", str(tmp_path / "x.txt")])


def test_legacy_translate_warns(fake_pipeline, scan, capsys):
    assert cli.legacy_translate([str(scan)]) == 0
    captured = capsys.readouterr()
    assert "deprecated" in captured.err and "netra-translate" in captured.err
    assert "[en2km] Annual Report" in captured.out


def test_serve_delegates_to_server(monkeypatch):
    import netra_translate.server.__main__ as server_main
    got = {}
    monkeypatch.setattr(server_main, "main", lambda argv=None: got.setdefault("argv", argv) and 0)
    cli.main(["serve", "--port", "9001"])
    assert "--port" in got["argv"] and "9001" in got["argv"]


def test_serve_forwards_worker_options(monkeypatch):
    import netra_translate.server.__main__ as server_main
    got = {}
    monkeypatch.setattr(server_main, "main", lambda argv=None: got.setdefault("argv", argv) and 0)
    cli.main(["serve", "--no-worker", "--threads", "2", "--config", "netra.yaml"])
    assert got["argv"] == ["--config", "netra.yaml", "--threads", "2", "--no-worker"]


def test_worker_command(monkeypatch, tmp_path):
    import netra_translate.server.worker as worker_module
    got = {}
    monkeypatch.setattr(worker_module, "main", lambda settings: got.setdefault("settings", settings) and 0)
    cli.main(["worker", "--data-dir", str(tmp_path / "jobs"), "--threads", "3"])
    assert got["settings"].data_dir == str(tmp_path / "jobs") and got["settings"].threads == 3


def test_worker_bad_config(tmp_path, capsys):
    cfg = tmp_path / "netra.yaml"
    cfg.write_text("server:\n  nope: 1\n", encoding="utf-8")
    assert cli.main(["worker", "--config", str(cfg)]) == 2
    assert "nope" in capsys.readouterr().err


def test_download(monkeypatch, capsys):
    import huggingface_hub
    calls = []
    monkeypatch.setattr(huggingface_hub, "hf_hub_download",
                        lambda repo, filename: calls.append((repo, filename)) or f"/cache/{filename}")
    assert cli.main(["download"]) == 0
    files = {f for _, f in calls}
    assert {"model.safetensors", "config.json"} <= files
    assert not any("doclayout" in f for f in files)
    assert "translator: /cache/model.safetensors" in capsys.readouterr().err
    calls.clear()
    assert cli.main(["download", "--layout"]) == 0
    assert any("doclayout" in f for _, f in calls)


# ── config ─────────────────────────────────────────────────────────────
def test_config_file_and_flags_override_it(fake_pipeline, scan, tmp_path):
    cfg = tmp_path / "netra.yaml"
    cfg.write_text("pipeline:\n  direction: km2en\n  mode: beam\n  beam_size: 3\n", encoding="utf-8")
    assert cli.main(["translate", "-i", str(scan), "--config", str(cfg)]) == 0
    assert fake_pipeline == {"direction": "km2en", "mode": "beam", "beam_size": 3}
    fake_pipeline.clear()
    assert cli.main(["translate", "-i", str(scan), "-c", str(cfg), "-d", "en2km", "--no-merge"]) == 0
    assert fake_pipeline["direction"] == "en2km" and fake_pipeline["merge_lines"] is False
    assert fake_pipeline["beam_size"] == 3


def test_flags_not_given_are_not_passed(fake_pipeline, scan):
    assert cli.main(["translate", "-i", str(scan)]) == 0
    assert fake_pipeline == {}


def test_config_unknown_key(fake_pipeline, scan, tmp_path, capsys):
    cfg = tmp_path / "netra.json"
    cfg.write_text(json.dumps({"pipeline": {"directon": "km2en"}}), encoding="utf-8")
    assert cli.main(["translate", "-i", str(scan), "--config", str(cfg)]) == 2
    assert "directon" in capsys.readouterr().err


def test_from_config_builds_pipeline(tmp_path):
    cfg = tmp_path / "netra.yaml"
    cfg.write_text("direction: km2en\nmerge_lines: false\n", encoding="utf-8")
    pipe = NetraTranslate.from_config(str(cfg), translator=FakeTranslator(), ocr=FakeOCR([]))
    assert pipe.direction == "km2en" and pipe.merge_lines is False


# ── batch ──────────────────────────────────────────────────────────────
def test_batch_directory_and_glob(fake_pipeline, tmp_path, capsys):
    src = tmp_path / "scans"
    src.mkdir()
    for name in ("a.png", "b.pdf", "notes.txt"):
        (src / name).write_bytes(b"fake")
    (tmp_path / "c.jpg").write_bytes(b"fake")
    out = tmp_path / "out"
    assert cli.main(["translate", "-i", str(src), str(tmp_path / "*.jpg"), "--save_path", str(out),
                     "-f", "txt"]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["a_translated.txt", "b_translated.txt", "c_translated.txt"]
    assert "3 of 3 files translated" in capsys.readouterr().err


def test_batch_needs_save_path(fake_pipeline, tmp_path, capsys):
    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"fake")
    assert cli.main(["translate", "-i", str(tmp_path / "a.png"), str(tmp_path / "b.png")]) == 2
    assert "--save_path" in capsys.readouterr().err


def test_batch_skips_a_failed_file(monkeypatch, sample_blocks, tmp_path, capsys):
    class Picky(FakeOCR):
        def process_document(self, source, **kw):
            if "bad" in str(source):
                raise ValueError("unreadable scan")
            return super().process_document(source, **kw)

    monkeypatch.setattr("netra_translate.pipeline.NetraTranslate",
                        lambda **kw: NetraTranslate(ocr=Picky(sample_blocks), translator=FakeTranslator()))
    for name in ("bad.png", "good.png", "good.jpg"):
        (tmp_path / name).write_bytes(b"fake")
    out = tmp_path / "out"
    assert cli.main(["translate", "-i", str(tmp_path / "*.*"), "--save_path", str(out), "-f", "json"]) == 1
    err = capsys.readouterr().err
    assert "bad.png: failed: unreadable scan" in err and "2 of 3 files translated" in err
    # good.jpg and good.png would both be good_translated: the second keeps its extension.
    assert sorted(p.name for p in out.iterdir()) == ["good_png_translated.json", "good_translated.json"]


def test_example_config_is_valid():
    from netra_translate.server.settings import Settings
    path = os.path.join(os.path.dirname(__file__), "..", "examples", "config.yaml")
    pipe = NetraTranslate.from_config(path, translator=FakeTranslator(), ocr=FakeOCR([]))
    assert pipe.direction == "auto"
    settings = Settings.from_config(path)
    assert settings.max_pages == 100 and settings.threads == 0
