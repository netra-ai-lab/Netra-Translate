import json

from conftest import FakeOCR, FakeTranslator, para

from netra_translate import NetraTranslate


def make(blocks, **kw):
    tr = FakeTranslator()
    return NetraTranslate(ocr=FakeOCR(blocks), translator=tr, **kw), tr


def test_auto_direction_per_block(sample_blocks):
    pipe, tr = make(sample_blocks)
    res = pipe.run("x.png")
    blocks = res.translated.blocks
    assert blocks[0]["text"] == "[en2km] Annual Report"
    assert blocks[1]["direction"] == "en2km"
    assert blocks[2]["text"] == "[km2en] ខ្ញុំទៅផ្សារ។"
    assert blocks[2]["source_text"] == "ខ្ញុំទៅផ្សារ។"


def test_forced_direction_is_passed_through(sample_blocks):
    pipe, tr = make(sample_blocks, direction="km2en")
    pipe.run("x.png")
    assert {d for _, d in tr.seen} == {"km2en"}


def test_table_cells_translated_and_empty_cells_kept(sample_blocks):
    res = make(sample_blocks)[0].run("x.png")
    table = res.translated.blocks[3]
    assert table["rows"] == [["[en2km] Name", "[en2km] 2024"], ["[km2en] ឈ្មោះ", ""]]
    assert table["source_rows"] == [["Name", "2024"], ["ឈ្មោះ", ""]]


def test_source_document_untouched(sample_blocks):
    res = make(sample_blocks)[0].run("x.png")
    assert res.source.blocks[1]["text"] == "The weather is nice today."
    assert "source_text" not in res.source.blocks[1]


def test_duplicate_text_translated_once():
    blocks = [para(0, "Hello"), para(1, "Hello", y=300)]
    pipe, tr = make(blocks)
    pipe.run("x.png")
    assert len(tr.seen) == 1


def test_lines_are_merged_before_translation():
    blocks = [para(0, "The weather is", 10, "line"), para(1, "nice today.", 58, "line")]
    pipe, tr = make(blocks)
    res = pipe.run("x.png")
    assert tr.seen == [("The weather is nice today.", "en2km")]
    assert len(res.translated.blocks) == 1


def test_merge_can_be_disabled():
    blocks = [para(0, "The weather is", 10, "line"), para(1, "nice today.", 58, "line")]
    pipe, tr = make(blocks, merge_lines=False)
    assert len(pipe.run("x.png").translated.blocks) == 2


def test_invalid_direction_rejected():
    import pytest
    with pytest.raises(ValueError):
        NetraTranslate(direction="fr2en", ocr=FakeOCR([]))


def test_exports(sample_blocks, tmp_path):
    res = make(sample_blocks)[0].run("x.png")
    data = json.loads(open(res.save(str(tmp_path / "o.json")), encoding="utf-8").read())
    assert data["blocks"][1]["source_text"] == "The weather is nice today."

    txt = open(res.save(str(tmp_path / "o.txt")), encoding="utf-8").read()
    assert "[en2km] Annual Report" in txt

    md = res.save(str(tmp_path / "o.md"), bilingual=True)
    text = open(md, encoding="utf-8").read()
    assert "The weather is nice today." in text and "[en2km] The weather is nice today." in text

    docx = res.save(str(tmp_path / "o.docx"), bilingual=True)
    from docx import Document as W
    paras = [p.text for p in W(docx).paragraphs]
    assert any("[en2km] The weather" in p for p in paras)
    assert any(p == "The weather is nice today." for p in paras)

    html = res.save(str(tmp_path / "o.html"))
    assert "[km2en]" in open(html, encoding="utf-8").read()


def test_bilingual_headings_keep_source_heading(sample_blocks):
    res = make(sample_blocks)[0].run("x.png")
    bi = res.bilingual_document().blocks
    assert [b["type"] for b in bi[:2]] == ["heading", "paragraph"]
    assert bi[0]["text"] == "Annual Report" and bi[1]["id"].endswith("-tr")


# ── PaddleOCR-style API ────────────────────────────────────────────────
def test_predict_returns_one_result_per_input(sample_blocks):
    pipe, _ = make(sample_blocks)
    results = pipe.predict(["a.png", "b.png"])
    assert len(results) == 2
    assert [r.input_path for r in results] == ["a.png", "b.png"]
    assert pipe.predict("a.png")[0].translated.blocks[0]["text"] == "[en2km] Annual Report"


def test_predict_accepts_bytes(sample_blocks):
    pipe, _ = make(sample_blocks)
    [res] = pipe.predict(b"\x89PNG fake")
    assert res.input_path is None and res._stem() == "translation"


def test_predict_iter_is_lazy(sample_blocks):
    pipe, _ = make(sample_blocks)
    it = pipe.predict_iter(["a.png", "b.png"])
    assert pipe.ocr.calls == []
    next(it)
    assert len(pipe.ocr.calls) == 1


def test_result_helpers(sample_blocks, tmp_path, capsys):
    [res] = make(sample_blocks)[0].predict(str(tmp_path / "letter.png"))
    res.print()
    assert "[en2km] The weather is nice today." in capsys.readouterr().out
    assert res.json == res.to_dict() and res.json["translate_version"] == 1

    out = tmp_path / "out"
    assert res.save_to_docx(str(out)).endswith("letter_translated.docx")
    assert json.loads(open(res.save_to_json(str(out)), encoding="utf-8").read())["blocks"]
    md = res.save_to_markdown(str(out / "custom.md"), bilingual=True)
    assert md.endswith("custom.md")
    assert (out / "letter_translated.docx").read_bytes()[:2] == b"PK"
