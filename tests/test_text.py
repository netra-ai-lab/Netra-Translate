from netra_translate import text


def test_detect_direction():
    assert text.detect_direction("សួស្តី ពិភពលោក") == text.KM2EN
    assert text.detect_direction("Hello world") == text.EN2KM
    assert text.detect_direction("12345") == text.EN2KM  # no letters -> default
    assert text.detect_direction("សួស្តី world hello again") == text.EN2KM


def test_reflow_khmer_joins_without_space():
    assert text.reflow_lines(["ខ្ញុំស្រលាញ់", "ប្រទេសកម្ពុជា"]) == "ខ្ញុំស្រលាញ់ប្រទេសកម្ពុជា"


def test_reflow_english_joins_with_space_and_dehyphenates():
    assert text.reflow_lines(["Hello", "world"]) == "Hello world"
    assert text.reflow_lines(["trans-", "lation works"]) == "translation works"
    assert text.reflow_lines(["", "  ", "a"]) == "a"


def test_split_sentences_english():
    assert text.split_sentences("Hello there. How are you? Fine!") == [
        "Hello there.",
        "How are you?",
        "Fine!",
    ]


def test_split_sentences_khmer():
    assert text.split_sentences("ខ្ញុំទៅផ្សារ។ គាត់នៅផ្ទះ។") == ["ខ្ញុំទៅផ្សារ។", "គាត់នៅផ្ទះ។"]


def test_split_keeps_decimals_together():
    assert text.split_sentences("Pi is 3.14 roughly. Done.") == ["Pi is 3.14 roughly.", "Done."]


def test_split_keeps_urls_together():
    assert text.split_sentences("See a.com/x?y=1 now. Ok") == ["See a.com/x?y=1 now.", "Ok"]


def test_has_letters():
    assert text.has_letters("p. 12a") and text.has_letters("ក")
    assert not text.has_letters("12/03/2024 -")


def test_chunk_sentence_short_is_unchanged():
    assert text.chunk_sentence("short", 50) == ["short"]


def test_chunk_sentence_long_respects_limit():
    long = ", ".join(["word " * 10] * 20)
    chunks = text.chunk_sentence(long, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert len(chunks) > 1


def test_chunk_sentence_khmer_hard_cut():
    chunks = text.chunk_sentence("ក" * 700, 300)
    assert [len(c) for c in chunks] == [300, 300, 100]
