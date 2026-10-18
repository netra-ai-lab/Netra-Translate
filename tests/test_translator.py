from netra_translate.translator import Translator


class Model:
    def __init__(self):
        self.calls = []

    def translate(self, text, direction, **kw):
        self.calls.append((text, direction, kw))
        return text.upper()


def test_paragraph_is_translated_sentence_by_sentence():
    m = Model()
    out, d = Translator(model=m).translate("Hello there. How are you?")
    assert [c[0] for c in m.calls] == ["Hello there.", "How are you?"]
    assert out == "HELLO THERE. HOW ARE YOU?" and d == "en2km"


def test_khmer_detected_and_split_on_khan():
    m = Model()
    _, d = Translator(model=m).translate("ខ្ញុំទៅផ្សារ។ គាត់នៅផ្ទះ។")
    assert d == "km2en" and len(m.calls) == 2


def test_no_letters_returned_as_is():
    m = Model()
    assert Translator(model=m).translate("12 / 03 / 2024")[0] == "12 / 03 / 2024"
    assert m.calls == []


def test_long_sentence_is_chunked():
    m = Model()
    Translator(model=m, max_chars=100).translate(", ".join(["alpha beta gamma"] * 30))
    assert len(m.calls) > 1 and all(len(c[0]) <= 100 for c in m.calls)


def test_decoding_options_forwarded():
    m = Model()
    Translator(model=m, mode="beam", beam_size=3, max_new_tokens=50).translate("Hi")
    assert m.calls[0][2] == {"mode": "beam", "beam_size": 3, "max_new_tokens": 50}
