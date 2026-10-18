[← Netra Translate](../README.md)

# Command line

```bash
netra-translate translate -i scan.jpg                            # print the translation
netra-translate translate -i scan.jpg --save_path output/        # output/scan_translated.docx
netra-translate translate -i letter.pdf --save_path output/ -f md --bilingual
netra-translate translate -i letter.pdf -o letter.docx --layout  # the extension picks the format
netra-translate translate -i scan.jpg -d km2en --mode beam --beam 5
netra-translate translate -i scans/ "more/*.pdf" --save_path output/   # many files, one result each
netra-translate translate -i scan.jpg --config netra.yaml
netra-translate download [--layout]
netra-translate serve --port 8000
netra-translate worker                                           # see Scaling
netra-translate version
```

| Option | Meaning |
| --- | --- |
| `-i`, `--input` | Images (JPG, PNG, TIFF, BMP, WebP) or PDFs; also directories and globs |
| `--save_path DIR` | Write to a directory, named after each input; `-f` picks the format (default `docx`) |
| `-c`, `--config` | A YAML or JSON file of pipeline options ([example](../examples/config.yaml)); flags override it |
| `-o FILE` | Write to a file; the extension picks the format (`.docx .html .md .txt .json`) |
| `-d`, `--direction` | `auto` (default; per block), `km2en` or `en2km` |
| `--bilingual` | Put the source next to each translated block |
| `--layout` | Layout analysis (needs the `layout` extra) |
| `--no-merge` | Don't merge OCR lines into paragraphs before translating |
| `--max-pages`, `--device`, `--detector`, `--mode`, `--beam`, `--ocr-beam` | Advanced |

`python -m netra_translate …` works the same way. With several inputs, `--save_path` is required. Each file prints a status line, a file that fails is reported and skipped, and the exit code is 1 if any failed. The models load once for the whole batch.
