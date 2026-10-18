"""The netra-ocr-mt preview names keep working for one release, with a warning."""
import importlib
import sys
import warnings

import netra_translate


def fresh_import(name):
    for mod in [m for m in sys.modules if m == "netra_ocr_mt" or m.startswith("netra_ocr_mt.")]:
        del sys.modules[mod]
    return importlib.import_module(name)


def test_old_package_warns_and_reexports():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        old = fresh_import("netra_ocr_mt")
    assert any(issubclass(w.category, DeprecationWarning) and "netra_translate" in str(w.message)
               for w in caught)
    assert old.OCRTranslator is netra_translate.NetraTranslate
    assert old.TranslationResult is netra_translate.TranslationResult


def test_old_submodules_resolve():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fresh_import("netra_ocr_mt")
        from netra_ocr_mt.merge import merge_lines
        from netra_ocr_mt.translator import Translator
    from netra_translate.merge import merge_lines as new_merge
    from netra_translate.translator import Translator as NewTranslator
    assert merge_lines is new_merge and Translator is NewTranslator


def test_ocr_translator_alias():
    assert netra_translate.OCRTranslator is netra_translate.NetraTranslate
