"""``netra-translate serve`` / ``python -m netra_translate.server``: run the web app + API."""
import argparse
import logging
import os
import threading


def add_settings_args(parser: argparse.ArgumentParser) -> None:
    """Options shared by ``serve`` and ``worker``."""
    parser.add_argument("--data-dir", help="Where jobs are stored (default ~/.cache/netra-translate/jobs)")
    parser.add_argument("--config", help="YAML/JSON config file (its server: options)")
    parser.add_argument("--threads", type=int, default=None,
                        help="torch CPU threads per worker (default: all cores)")


def build_settings(args):
    """Settings from, in order of precedence: flags, --config, NETRA_* env, defaults."""
    from .settings import Settings
    overrides = {}
    if args.data_dir:
        overrides["data_dir"] = args.data_dir
    if args.threads is not None:
        overrides["threads"] = args.threads
    if getattr(args, "no_worker", False):
        overrides["embedded_worker"] = False
    if args.config:
        return Settings.from_config(args.config, **overrides)
    return Settings(**overrides)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netra-translate serve",
                                     description="Run the Netra Translate web app and REST API.")
    parser.add_argument("--host", default=os.environ.get("NETRA_HOST", "127.0.0.1"),
                        help="Interface to bind (default 127.0.0.1; use 0.0.0.0 to allow other machines)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("NETRA_PORT", 8000)))
    parser.add_argument("--no-worker", action="store_true",
                        help="Don't run jobs in this process; start `netra-translate worker` processes "
                             "on the same --data-dir instead")
    parser.add_argument("--open", action="store_true", help="Open the app in your browser")
    add_settings_args(parser)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        import uvicorn
    except ImportError as e:
        raise SystemExit("The web app needs the 'server' extra: pip install \"netra-translate[server]\"") from e
    try:
        settings = build_settings(args)
    except (OSError, ValueError) as e:
        raise SystemExit(f"error: {e}") from e
    from .app import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    url = f"http://{'localhost' if args.host in ('0.0.0.0', '127.0.0.1') else args.host}:{args.port}"
    print(f"Netra Translate: open {url}")
    if not settings.embedded_worker:
        print(f"No worker in this process: start `netra-translate worker --data-dir {settings.data_dir}` "
              "to run jobs.")
    if os.path.exists("/.dockerenv"):
        # Inside a container the URL above only works if the port was published.
        print(f"Running in Docker: start the container with -p {args.port}:{args.port} "
              f"(Docker Desktop: Optional settings → Host port {args.port}), or the page won't open.")
    if args.open:
        import webbrowser
        threading.Timer(2.0, webbrowser.open, [url]).start()
    # One API process. Jobs run in a worker: a thread in this process, or
    # separate `netra-translate worker` processes (see server/worker.py).
    uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
