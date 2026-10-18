"""Translate one scan or PDF and save it as Word.

    python examples/translate_file.py letter.pdf [output/]
"""
import sys

from netra_translate import NetraTranslate

source = sys.argv[1]
out_dir = sys.argv[2] if len(sys.argv) > 2 else "output"

pipe = NetraTranslate(direction="auto")     # layout=True for headings, tables and reading order
for result in pipe.predict(source):
    result.print()                          # translated text
    print("Saved", result.save_to_docx(out_dir))
    result.save_to_json(out_dir)            # blocks, boxes, source and translated text
