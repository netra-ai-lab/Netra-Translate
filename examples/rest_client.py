"""Translate a file on a running server (netra-translate serve).

    pip install "netra-translate[client]"
    python examples/rest_client.py letter.pdf [http://localhost:8000]

Set NETRA_API_KEY if the server requires a key.
"""
import os
import sys

from netra_translate import Client

source = sys.argv[1]
server = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

with Client(server, api_key=os.environ.get("NETRA_API_KEY")) as client:
    info = client.info()
    print(f"{info['name']} {info['version']} on {info['device_name']}, {len(info['workers'])} worker(s)")

    out = client.translate(source, direction="auto")        # uploads, then waits for the result
    job = out["job"]
    print(f"{job['filename']}: {job['pages']} page(s), {len(out['result']['blocks'])} blocks")

    target = f"{job['filename']}_translated.docx"
    with open(target, "wb") as f:
        f.write(client.export(job["id"], "docx", bilingual=True))
    print("Saved", target)
