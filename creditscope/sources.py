"""The list of sources and how to download them."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import ETFS, NASDAQ_URL, USER_AGENT


@dataclass(frozen=True)
class Source:
    name: str      # raw file stem, e.g. "nasdaq-SPY"
    provider: str  # "nasdaq"
    item_id: str   # "SPY"
    url: str
    fmt: str       # "json"


def all_sources():
    return [
        Source(f"nasdaq-{sym}", "nasdaq", sym, NASDAQ_URL.format(symbol=sym), "json")
        for sym, _a, _c in ETFS
    ]


def http_get(url: str, timeout: int = 20, retries: int = 3, backoff: float = 3.0) -> bytes:
    """Download a URL and return the body bytes. Raises on failure after retries."""
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"download failed after {retries} attempts: {last}")
