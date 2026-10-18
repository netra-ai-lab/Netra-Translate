from netra_ocr.document import Document

from netra_translate.merge import merge_lines


def line(i, text, y, page=0, x1=10, x2=400, h=40):
    bbox = [x1, y, x2, y + h]
    return {"id": f"p{page}-b{i}", "type": "paragraph", "page": page, "bbox": bbox,
            "text": text, "label": "line", "lines": [{"text": text, "bbox": bbox}]}


def doc(*blocks):
    return Document(pages=[{"index": 0, "width": 500, "height": 500, "image": None}],
                    blocks=list(blocks))


def test_wrapped_sentence_is_merged():
    d = merge_lines(doc(line(0, "The weather is", 10), line(1, "nice today.", 58)))
    assert len(d.blocks) == 1
    assert d.blocks[0]["text"] == "The weather is\nnice today."
    assert d.blocks[0]["bbox"] == [10, 10, 400, 98]
    assert len(d.blocks[0]["lines"]) == 2


def test_sentence_end_breaks_paragraph():
    d = merge_lines(doc(line(0, "First sentence.", 10), line(1, "Second one", 58)))
    assert len(d.blocks) == 2


def test_khmer_khan_breaks_paragraph():
    d = merge_lines(doc(line(0, "ខ្ញុំទៅផ្សារ។", 10), line(1, "គាត់នៅផ្ទះ។", 58)))
    assert len(d.blocks) == 2


def test_large_gap_breaks_paragraph():
    d = merge_lines(doc(line(0, "unfinished", 10), line(1, "far below", 300)))
    assert len(d.blocks) == 2


def test_different_column_breaks_paragraph():
    d = merge_lines(doc(line(0, "left column", 10, x1=10, x2=200),
                        line(1, "right column", 58, x1=300, x2=490)))
    assert len(d.blocks) == 2


def test_other_pages_and_types_untouched():
    figure = {"id": "f", "type": "figure", "page": 0, "bbox": [0, 60, 5, 70], "image": None}
    d = merge_lines(doc(line(0, "open", 10), figure, line(1, "next", 58)))
    assert [b["type"] for b in d.blocks] == ["paragraph", "figure", "paragraph"]


def test_input_is_not_mutated():
    src = doc(line(0, "a", 10), line(1, "b", 58))
    merge_lines(src)
    assert len(src.blocks) == 2 and src.blocks[0]["text"] == "a"
