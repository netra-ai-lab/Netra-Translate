[← Netra Translate](../README.md)

# Python API

```python
from netra_translate import NetraTranslate

pipeline = NetraTranslate(direction="auto")       # models load on first use, once
for res in pipeline.predict("letter.pdf"):        # a path, bytes, or a list of them
    res.print()                                   # translated text
    res.save_to_docx("output/")                   # output/letter_translated.docx
    res.save_to_markdown("output/", bilingual=True)
    res.save_to_json("output/")

data = res.json                                   # the translated document as a dict
for block in res.translated.blocks:
    print(block["type"], block.get("source_text"), "->", block.get("text"))
```

| | |
| --- | --- |
| `NetraTranslate(direction, layout, detector, device, mode, beam_size, merge_lines)` | The pipeline |
| `NetraTranslate.from_config("netra.yaml", **overrides)` | The same, from a config file |
| `.predict(input)` / `.predict_iter(input)` | List of `TranslationResult`, or a generator over them for many files |
| `res.print(bilingual=False)`, `res.text`, `res.json` | Read the result |
| `res.save_to_docx / save_to_markdown / save_to_json(path)` | `path` is a directory (the file is named after the input) or a file path |
| `res.save(path)`, `res.export(fmt)` | Any format, or `(bytes, filename, mimetype)` |

The JSON is Netra-OCR's document schema. Translated text blocks add `source_text` and `direction`, and tables add `source_rows`. More in [examples/](../examples/).

**Client for a running server** (the `client` extra):

```python
from netra_translate import Client

with Client("http://localhost:8000", api_key=None) as client:
    out = client.translate("letter.pdf", direction="km2en")   # uploads, waits, returns {"job", "result"}
    open("letter.docx", "wb").write(client.export(out["job"]["id"], "docx"))
```

`Client` also has `submit`, `job`, `wait`, `result`, `retranslate`, `delete`, `jobs`, `info` and `ready`. Errors raise `NetraAPIError` with the HTTP status and the server's message.
