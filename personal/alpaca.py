"""Minimal Alpaca market-data client (standard library only).

Endpoints used (all from Alpaca's current documentation, fetched 2026-11-14):
  GET {DATA}/v2/stocks/bars            multi-symbol historical bars; adjustment=raw|split|dividend|spin-off|all (default raw!)
  GET {DATA}/v1/corporate-actions      cash dividends and splits (filtered by process_date)
  GET {TRADING}/v2/assets              tradable symbols and names (needs a paper or live key)
  GET {TRADING}/v2/account             verifies the credentials
Auth: headers APCA-API-KEY-ID / APCA-API-SECRET-KEY. Basic plan: 200 historical calls per minute, HTTP 429 when exceeded.

The HTTP layer is injectable so tests never touch the network, and the secret never appears in URLs, errors or logs.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from .credentials import Credentials

DATA_URL = os.environ.get("ALPACA_DATA_URL", "https://data.alpaca.markets")
TRADING_URL = os.environ.get("ALPACA_TRADING_URL", "https://paper-api.alpaca.markets")
BARS_PAGE_LIMIT = 10000          # documented maximum for the bars endpoint
ACTIONS_PAGE_LIMIT = 1000        # documented maximum for corporate actions
CASH_DIVIDEND = "cash_dividend"
SPLIT_TYPES = ("forward_split", "reverse_split", "unit_split")


class AlpacaError(Exception):
    """An API failure. The message is safe to print (it never contains credentials)."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class Response:
    def __init__(self, status: int, body: bytes, headers: Optional[dict] = None):
        self.status, self.body, self.headers = status, body, {k.lower(): v for k, v in (headers or {}).items()}


def default_opener(request: urllib.request.Request, timeout: float = 30) -> Response:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return Response(r.status, r.read(), dict(r.headers))
    except urllib.error.HTTPError as e:
        return Response(e.code, e.read(), dict(e.headers or {}))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AlpacaError("network error talking to Alpaca: " + type(e).__name__) from None


class Client:
    def __init__(self, creds: Credentials, opener: Callable = default_opener, sleep: Callable = time.sleep,
                 min_interval: float = 0.35, max_retries: int = 4, data_url: Optional[str] = None, trading_url: Optional[str] = None):
        self.data_url = data_url or os.environ.get("ALPACA_DATA_URL", DATA_URL)
        self.trading_url = trading_url or os.environ.get("ALPACA_TRADING_URL", TRADING_URL)
        self._headers = {"APCA-API-KEY-ID": creds.key_id, "APCA-API-SECRET-KEY": creds.secret, "Accept": "application/json"}
        self._opener, self._sleep = opener, sleep
        self._min_interval, self._max_retries = min_interval, max_retries      # 0.35 s ~ 170 calls/min, under the 200/min Basic limit
        self._last = 0.0

    # ---------- transport ----------
    def _get(self, base: str, path: str, params: Optional[dict] = None) -> dict:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = base.rstrip("/") + path + ("?" + query if query else "")
        for attempt in range(self._max_retries + 1):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            resp = self._opener(urllib.request.Request(url, headers=self._headers))
            if resp.status == 200:
                try:
                    return json.loads(resp.body)
                except ValueError:
                    raise AlpacaError("Alpaca returned a response that is not valid JSON", 200) from None
            if resp.status == 429 or resp.status >= 500:
                if attempt < self._max_retries:
                    reset = resp.headers.get("x-ratelimit-reset")
                    delay = 2.0 * (attempt + 1)
                    if reset and reset.isdigit():
                        delay = max(1.0, min(65.0, float(reset) - time.time() + 0.5))
                    self._sleep(delay)
                    continue
            raise AlpacaError(self._explain(resp), resp.status)
        raise AlpacaError("Alpaca request failed after retries")

    @staticmethod
    def _explain(resp: Response) -> str:
        detail = ""
        try:
            detail = str(json.loads(resp.body).get("message", ""))[:200]
        except (ValueError, AttributeError):
            pass
        hints = {
            401: "Alpaca rejected the credentials (HTTP 401). Check the key ID and secret, and that they are PAPER keys if you used paper-api.",
            403: "Alpaca refused this request (HTTP 403): the key may lack permission for this data or feed.",
            404: "Alpaca returned HTTP 404 (not found).",
            422: "Alpaca rejected the request parameters (HTTP 422).",
            429: "Alpaca rate limit exceeded (HTTP 429) and retries were exhausted.",
        }
        msg = hints.get(resp.status, f"Alpaca returned HTTP {resp.status}.")
        return msg + (f" Detail: {detail}" if detail else "")

    # ---------- endpoints ----------
    def account(self) -> dict:
        return self._get(self.trading_url, "/v2/account")

    def assets(self) -> list:
        data = self._get(self.trading_url, "/v2/assets", {"status": "active", "asset_class": "us_equity"})
        if not isinstance(data, list):
            raise AlpacaError("unexpected assets response")
        return data

    def bars(self, symbols: list, start: str, end: str, adjustment: str = "split", feed: str = "sip",
             timeframe: str = "1Day") -> dict:
        """symbol -> list of bars ({t,o,h,l,c,v,...}) for the whole range, following pagination."""
        out = {s: [] for s in symbols}
        token = None
        while True:
            data = self._get(self.data_url, "/v2/stocks/bars", {
                "symbols": ",".join(symbols), "timeframe": timeframe, "start": start, "end": end,
                "limit": BARS_PAGE_LIMIT, "adjustment": adjustment, "feed": feed, "sort": "asc", "page_token": token})
            for sym, rows in (data.get("bars") or {}).items():
                out.setdefault(sym, []).extend(rows or [])
            token = data.get("next_page_token")
            if not token:
                return out

    def corporate_actions(self, symbols: list, start: str, end: str) -> dict:
        """{'dividends': {sym: [{ex_date, rate, ...}]}, 'splits': {sym: [{ex_date, ratio}]}}. Dates filter on process_date."""
        types = ",".join((CASH_DIVIDEND,) + SPLIT_TYPES)
        dividends = {s: [] for s in symbols}
        splits = {s: [] for s in symbols}
        token = None
        while True:
            data = self._get(self.data_url, "/v1/corporate-actions", {
                "symbols": ",".join(symbols), "types": types, "start": start, "end": end,
                "limit": ACTIONS_PAGE_LIMIT, "sort": "asc", "page_token": token})
            ca = data.get("corporate_actions") or {}
            for row in ca.get("cash_dividends") or []:
                dividends.setdefault(row.get("symbol"), []).append(row)
            for kind in ("forward_splits", "reverse_splits", "unit_splits"):
                for row in ca.get(kind) or []:
                    try:
                        ratio = float(row["new_rate"]) / float(row["old_rate"])
                    except (KeyError, TypeError, ValueError, ZeroDivisionError):
                        continue
                    splits.setdefault(row.get("symbol"), []).append({"ex_date": row.get("ex_date"), "ratio": ratio})
            token = data.get("next_page_token")
            if not token:
                return {"dividends": dividends, "splits": splits}
