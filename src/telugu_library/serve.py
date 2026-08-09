"""Serving the built site locally.

    python -m telugu_library.serve

Exists so that reading the library needs no explanation. `python -m http.server` works
too, but it defaults to the working directory, and running it from the repository root
serves the source code instead of the site — which looks like the build failed.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--site", type=Path, default=SITE)
    args = parser.parse_args(argv)

    if not (args.site / "index.html").exists():
        sys.exit(
            f"no site at {args.site}.\n"
            "  PYTHONPATH=src python3 -m telugu_library.build"
        )

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(args.site)
    )
    # Without this a restart fails with "Address already in use" for a minute or so,
    # which during development is the common case rather than the rare one.
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", args.port), handler) as server:
        print(f"తెలుగు గ్రంథాలయం → http://localhost:{args.port}/")
        print("Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
