[← Netra Translate](../README.md)

# Migrating from netra-ocr-mt

The preview releases were called `netra-ocr-mt`. The old names still work in 1.0, with a deprecation warning, and will be removed in the next release.

| Before | Now |
| --- | --- |
| `pip install netra-ocr-mt[server]` | `pip install netra-translate[server]` (or `[all]`) |
| `from netra_ocr_mt import OCRTranslator` | `from netra_translate import NetraTranslate` |
| `OCRTranslator().run(path)` | `NetraTranslate().predict(path)` (`run` still works) |
| `ocr-translate scan.jpg -o out.docx` | `netra-translate translate -i scan.jpg -o out.docx` |
| `ocr-translate-web` | `netra-translate serve` |
| `POST /v1/ocr-translate` | `POST /v1/translate`, then `GET /v1/jobs/{id}/export` |
| `/v1/results/{id}/…` | `/v1/jobs/{id}/…` |
| `NETRA_MAX_RESULTS` | `NETRA_JOB_TTL_HOURS` (jobs are stored on disk) |
