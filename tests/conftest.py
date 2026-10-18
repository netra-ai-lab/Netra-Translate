import pytest
from netra_ocr.document import Document


class FakeOCR:
    """Stands in for KhmerOCRPipeline: returns a fixed Document."""

    def __init__(self, blocks):
        self.blocks = blocks
        self.calls = []

    def process_document(self, source, **kwargs):
        self.calls.append((source, kwargs))
        return Document(pages=[{"index": 0, "width": 500, "height": 500, "image": None}],
                        blocks=[dict(b) for b in self.blocks])


class FakeTranslator:
    """Stands in for Translator: tags text so tests can see what was translated."""

    def __init__(self):
        self.seen = []

    def translate(self, text, direction="auto"):
        from netra_translate import text as T
        if direction == "auto":
            direction = T.detect_direction(text)
        self.seen.append((text, direction))
        return f"[{direction}] {text}", direction


def para(i, text, y=10, label="paragraph"):
    bbox = [10, y, 400, y + 40]
    return {"id": f"p0-b{i}", "type": "paragraph", "page": 0, "bbox": bbox, "text": text,
            "label": label, "lines": [{"text": text, "bbox": bbox}], "align": "left"}


@pytest.fixture
def sample_blocks():
    return [
        {**para(0, "Annual Report"), "type": "heading", "level": 1},
        para(1, "The weather is nice today."),
        para(2, "ខ្ញុំទៅផ្សារ។"),
        {"id": "p0-b3", "type": "table", "page": 0, "bbox": None, "image": None,
         "rows": [["Name", "2024"], ["ឈ្មោះ", ""]]},
    ]
