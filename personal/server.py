"""Localhost-only server for the personal edition.

It serves the public site files (an allowlist, not the whole repo) plus the PRIVATE data directory at /private-data/ and an
on-demand endpoint /api/series/<SYMBOL>. Safeguards:
  * binds to a loopback address only (refuses anything else),
  * rejects requests whose Host header is not localhost/127.0.0.1 (DNS-rebinding guard),
  * only serves allow-listed site paths; never .git, source code, docs or the credentials,
  * private responses are marked no-store and never contain credentials,
  * the public site and GitHub Pages never include these paths.
"""
from __future__ import annotations

import json
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlsplit

from . import build, config, service

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
SITE_FILES = {"index.html", "browse.html", "trends.html", "explorer.html", "manifest.webmanifest", "sw.js",
              "data/history.csv", "data/status.json"}
SITE_PREFIXES = ("assets/", "explorer/sample/")
SERIES_FILE = re.compile(r"^series/[A-Z0-9][A-Z0-9.\-]{0,9}\.json$")


def is_allowed_site_path(rel: str) -> bool:
    return rel in SITE_FILES or any(rel.startswith(p) for p in SITE_PREFIXES) and ".." not in rel


class Handler(BaseHTTPRequestHandler):
    server_version = "CreditScopePersonal"
    sys_version = ""

    def log_message(self, fmt, *args):                      # no request logging: nothing private should reach a terminal log
        pass

    # ---------- helpers ----------
    def _send(self, status: int, body: bytes, ctype: str = "application/json", private: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store" if private else "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj, private: bool = True):
        self._send(status, json.dumps(obj).encode(), "application/json", private)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        name = host.rsplit(":", 1)[0].strip("[]") if not host.startswith("[") else host.split("]")[0].strip("[")
        return name in LOOPBACK

    # ---------- routing ----------
    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "forbidden host"})
        path = unquote(urlsplit(self.path).path)
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/")
        if "\x00" in rel or ".." in rel.split("/") or "\\" in rel:
            return self._json(400, {"error": "bad path"})
        if rel == "api/health":
            return self._json(200, {"personal": True, "ready": (self.server.data_dir / "index.json").exists()})
        if rel.startswith("api/series/"):
            return self._api_series(rel[len("api/series/"):].upper())
        if rel == "private-data/index.json":
            return self._file(self.server.data_dir / "index.json", private=True)
        if rel.startswith("private-data/"):
            sub = rel[len("private-data/"):]
            if SERIES_FILE.match(sub):
                return self._file(self.server.data_dir / sub, private=True)
            return self._json(404, {"error": "not found"})
        if is_allowed_site_path(rel):
            return self._file(self.server.site_root / rel)
        return self._json(404, {"error": "not found"}, private=False)

    def _file(self, path: Path, private: bool = False):
        try:
            resolved = path.resolve()
            base = (self.server.data_dir if private else self.server.site_root).resolve()
            resolved.relative_to(base)
            body = resolved.read_bytes()
        except (OSError, ValueError):
            return self._json(404, {"error": "not found"}, private=private)
        if not private and resolved.name == "explorer.html":
            # marks the page so it looks for private data; the public site and plain static servers never carry this marker
            body = body.replace(b"<head>", b'<head>\n<meta name="creditscope-personal" content="1">', 1)
        ctype = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        if resolved.suffix == ".webmanifest":
            ctype = "application/manifest+json"
        self._send(200, body, ctype + ("; charset=utf-8" if ctype.startswith("text/") or "json" in ctype or "javascript" in ctype else ""), private)

    def _api_series(self, symbol: str):
        """Fresh cached copy, else fetch on demand; if Alpaca cannot be reached (no credentials, offline, error) serve a stale copy."""
        if symbol.endswith(".JSON"):
            symbol = symbol[:-5]
        if not service.SYMBOL.match(symbol):
            return self._json(400, {"error": "invalid symbol"})
        data = self.server.data_dir
        series = service.cached_series(data, symbol)
        if series is None:
            stale = build.read_series(data, symbol)
            client = self.server.client_factory() if self.server.client_factory else None
            if client is None:
                if stale:
                    return self._json(200, stale)
                return self._json(404, {"error": "symbol is not synced and no credentials are configured (python -m personal setup)"})
            try:
                series = service.fetch_symbol(client, symbol, data, self.server.feed())
            except Exception as e:                           # AlpacaError messages are secret-free by construction
                if stale:
                    return self._json(200, stale)
                return self._json(502, {"error": str(e)[:300]})
            series = series or stale
        if not series:
            return self._json(404, {"error": f"no data for {symbol}"})
        self._json(200, series)


class PersonalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host: str, port: int, site_root: Path, data_dir: Path,
                 client_factory: Optional[Callable] = None, feed: Callable = lambda: "iex"):
        if host not in LOOPBACK:
            raise ValueError("the personal server only binds to loopback addresses (127.0.0.1 / localhost)")
        super().__init__((host, port), Handler)
        self.site_root, self.data_dir = Path(site_root), Path(data_dir)
        self.client_factory, self.feed = client_factory, feed


def serve_in_thread(server: PersonalServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t
