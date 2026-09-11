"""Local static host for the zero-API Living Office viewer."""

from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "WEB"
DEFAULT_PORT = 8000


class StaticViewerHandler(SimpleHTTPRequestHandler):
    """Serve WEB assets and map the site root to the browser viewer."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _map_viewer_root(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in {"", "/", "/index.html"}:
            self.path = "/viewer.html"
            if parsed.query:
                self.path += f"?{parsed.query}"

    def do_GET(self) -> None:
        self._map_viewer_root()
        super().do_GET()

    def do_HEAD(self) -> None:
        self._map_viewer_root()
        super().do_HEAD()


def main() -> int:
    if not WEB_ROOT.is_dir():
        raise SystemExit(f"Missing WEB directory: {WEB_ROOT}")

    server = ThreadingHTTPServer(("127.0.0.1", DEFAULT_PORT), StaticViewerHandler)
    print(f"Static Living Office viewer: http://127.0.0.1:{DEFAULT_PORT}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
