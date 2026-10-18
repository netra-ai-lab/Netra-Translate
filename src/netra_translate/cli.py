"""``netra-translate`` command line.

    netra-translate translate -i scan.jpg --save_path output/
    netra-translate translate -i letter.pdf -o letter.docx --bilingual --layout
    netra-translate translate -i scans/ "more/*.pdf" --save_path output/ -f md
    netra-translate translate -i scan.jpg --config netra.yaml
    netra-translate download --layout
    netra-translate serve --port 8000
    netra-translate serve --no-worker  &  netra-translate worker
    netra-translate version
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

from .pipeline import DIRECTIONS
from .result import FORMATS

# What `translate` picks up from a directory.
INPUT_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")


def _add_translate_args(p: argparse.ArgumentParser) -> None:
    # Defaults are None so a --config file can fill in whatever isn't given here.
    p.add_argument("input_pos", nargs="*", metavar="INPUT", help=argparse.SUPPRESS)
    p.add_argument("-i", "--input", nargs="+", default=[],
                   help="Images (JPG/PNG/TIFF/BMP/WebP) or PDFs; also directories and globs")
    out = p.add_mutually_exclusive_group()
    out.add_argument("--save_path", "--save-path", dest="save_path",
                     help="Directory to write results to (named after each input)")
    out.add_argument("-o", "--output",
                     help="Output file; the extension picks the format (.json .txt .md .html .docx)")
    p.add_argument("-f", "--format", default=None, choices=FORMATS,
                   help="Format written to --save_path (default: docx)")
    p.add_argument("-c", "--config", help="YAML/JSON config file (its pipeline: options); flags override it")
    p.add_argument("-d", "--direction", default=None, choices=DIRECTIONS,
                   help="auto detects Khmer vs English per block (default)")
    p.add_argument("--bilingual", action="store_true",
                   help="Put each source block next to its translation (txt/md/html/docx)")
    p.add_argument("--layout", action="store_true", default=None,
                   help="Layout analysis (headings, paragraphs, tables); needs the layout extra")
    p.add_argument("--detector", default=None, choices=["yolo", "tesseract", "legacy"])
    p.add_argument("--no-merge", dest="merge_lines", action="store_false", default=None,
                   help="Do not merge consecutive OCR lines into paragraphs before translating")
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--mode", default=None, choices=["greedy", "beam"], help="Translation decoding")
    p.add_argument("--beam", dest="beam_size", type=int, default=None, help="Beam size when --mode beam")
    p.add_argument("--ocr-beam", type=int, default=None, help="OCR beam width")
    p.add_argument("--device", default=None, help="cpu | cuda (default: auto)")


def build_parser() -> argparse.ArgumentParser:
    from .server.__main__ import add_settings_args

    p = argparse.ArgumentParser(
        prog="netra-translate",
        description="Netra Translate: OCR an image or PDF and translate it (Khmer <-> English).")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True
    _add_translate_args(sub.add_parser("translate", help="Translate files",
                                       description="OCR files and translate them."))
    d = sub.add_parser("download", help="Download the models ahead of time",
                       description="Download the models into the Hugging Face cache (HF_HOME), "
                                   "so later runs work offline with HF_HUB_OFFLINE=1.")
    d.add_argument("--layout", action="store_true", help="Also download the layout model")
    s = sub.add_parser("serve", help="Run the web app and REST API",
                       description="Run the Netra Translate web app and REST API.")
    s.add_argument("--host", default=None, help="Interface to bind (default 127.0.0.1)")
    s.add_argument("--port", type=int, default=None, help="Port (default 8000)")
    s.add_argument("--no-worker", action="store_true",
                   help="Don't run jobs in this process; start `netra-translate worker` processes instead")
    s.add_argument("--open", action="store_true", help="Open the app in your browser")
    add_settings_args(s)
    w = sub.add_parser("worker", help="Run a worker that processes the server's jobs",
                       description="Run jobs queued by `netra-translate serve --no-worker`. Start as "
                                   "many as the machine has room for, on the same --data-dir.")
    add_settings_args(w)
    sub.add_parser("version", help="Print the version")
    return p


def _expand(patterns: list[str]) -> tuple[list[str], list[str]]:
    """Files named by ``patterns`` (files, directories, globs), and the patterns that matched nothing."""
    files, missing = [], []
    for pattern in patterns:
        if os.path.isdir(pattern):
            found = sorted(os.path.join(pattern, f) for f in os.listdir(pattern)
                           if f.lower().endswith(INPUT_EXTENSIONS)
                           and os.path.isfile(os.path.join(pattern, f)))
        elif os.path.isfile(pattern):
            found = [pattern]
        else:
            found = sorted(f for f in glob.glob(pattern) if os.path.isfile(f))
        if not found:
            missing.append(pattern)
        for f in found:
            if f not in files:
                files.append(f)
    return files, missing


def _pipeline_options(args) -> dict:
    """Flags that were given, as NetraTranslate arguments."""
    given = {"detector": args.detector, "layout": args.layout, "direction": args.direction,
             "device": args.device, "mode": args.mode, "beam_size": args.beam_size,
             "ocr_beam": args.ocr_beam, "merge_lines": args.merge_lines}
    return {k: v for k, v in given.items() if v is not None}


def _translate(args) -> int:
    patterns = [*args.input, *args.input_pos]
    if not patterns:
        print("error: no input file; use -i FILE", file=sys.stderr)
        return 2
    files, missing = _expand(patterns)
    for pattern in missing:
        print(f"error: file not found: {pattern}", file=sys.stderr)
    if missing:
        return 2
    if len(files) > 1 and not args.save_path:
        print(f"error: {len(files)} input files; use --save_path DIR to write one result per file",
              file=sys.stderr)
        return 2
    from .pipeline import NetraTranslate

    try:
        options = _pipeline_options(args)
        pipe = NetraTranslate.from_config(args.config, **options) if args.config else NetraTranslate(**options)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if len(files) == 1:
        result = pipe.predict(files[0], max_pages=args.max_pages)[0]
        if args.output:
            path = result.save(args.output, bilingual=args.bilingual)
        elif args.save_path:
            path = result._save_to(args.save_path, args.format or "docx", args.bilingual)
        else:
            result.print(bilingual=args.bilingual)
            return 0
        print(f"Saved {path}", file=sys.stderr)
        return 0

    # Batch: one result per file; a file that fails is reported and skipped.
    failed, used = 0, set()
    for n, source in enumerate(files, 1):
        prefix = f"[{n}/{len(files)}] {source}"
        try:
            result = pipe.predict(source, max_pages=args.max_pages)[0]
            stem = result._stem()
            if stem in used:    # scan.pdf and scan.jpg: keep both
                stem = os.path.basename(source).replace(".", "_") + "_translated"
            used.add(stem)
            path = result.save(os.path.join(args.save_path, stem + "." + (args.format or "docx")),
                               bilingual=args.bilingual)
        except Exception as e:  # noqa: BLE001 - one bad file shouldn't stop the batch
            failed += 1
            print(f"{prefix}: failed: {e or type(e).__name__}", file=sys.stderr)
            continue
        print(f"{prefix} -> {path}", file=sys.stderr)
    print(f"{len(files) - failed} of {len(files)} files translated", file=sys.stderr)
    return 1 if failed else 0


def _download(args) -> int:
    from .models import download
    download(layout=args.layout, log=lambda line: print(line, file=sys.stderr))
    return 0


def _serve(args) -> int:
    from .server.__main__ import main as serve
    argv = []
    for flag, value in (("--host", args.host), ("--port", args.port), ("--data-dir", args.data_dir),
                        ("--config", args.config), ("--threads", args.threads)):
        if value is not None:
            argv += [flag, str(value)]
    for flag, on in (("--no-worker", args.no_worker), ("--open", args.open)):
        if on:
            argv.append(flag)
    serve(argv)
    return 0


def _worker(args) -> int:
    from .server.__main__ import build_settings
    from .server.worker import main as worker
    try:
        settings = build_settings(args)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return worker(settings)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    commands = {"translate": _translate, "download": _download, "serve": _serve, "worker": _worker}
    if args.command in commands:
        return commands[args.command](args)
    from . import __version__
    print(f"netra-translate {__version__}")
    return 0


# ── deprecated entry points (netra-ocr-mt previews) ────────────────────
def _deprecated(old: str, new: str) -> None:
    print(f"warning: '{old}' is deprecated and will be removed in the next release; "
          f"use '{new}'.", file=sys.stderr)


def legacy_translate(argv=None) -> int:
    """``ocr-translate FILE ...`` -> ``netra-translate translate FILE ...``"""
    _deprecated("ocr-translate", "netra-translate translate")
    return main(["translate", *(sys.argv[1:] if argv is None else argv)])


def legacy_serve(argv=None) -> int:
    """``ocr-translate-web ...`` -> ``netra-translate serve ...``"""
    _deprecated("ocr-translate-web", "netra-translate serve")
    return main(["serve", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
