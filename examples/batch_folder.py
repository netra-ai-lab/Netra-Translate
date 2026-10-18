"""Translate every scan and PDF in a folder, one Word file each.

    python examples/batch_folder.py scans/ output/

Same as: netra-translate translate -i scans/ --save_path output/
The models load once and are reused for every file.
"""
import pathlib
import sys

from netra_translate import NetraTranslate

src, out_dir = pathlib.Path(sys.argv[1]), sys.argv[2]
files = sorted(p for p in src.iterdir()
               if p.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"})

pipe = NetraTranslate()
# predict_iter yields each result as soon as it's ready.
for path, result in zip(files, pipe.predict_iter(files)):
    print(f"{path.name} -> {result.save_to_docx(out_dir)}")
