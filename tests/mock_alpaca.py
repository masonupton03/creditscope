"""A mock Alpaca API for tests and local end-to-end checks (never contacts the real service).

It implements the documented behaviour the personal edition depends on: header authentication, /v2/account, /v2/assets,
/v2/stocks/bars (symbols, start, end, limit, adjustment raw|split|all, feed sip|iex, paging), /v1/corporate-actions
(cash dividends, forward splits, paging), HTTP 429 with X-RateLimit-Reset, and the 403 "subscription does not permit
querying recent SIP data" case for accounts that only have the IEX feed. Bars come from the simulated sample series.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SAMPLE = Path(__file__).resolve().parent.parent / "explorer" / "sample"
KEY_ID, SECRET = "TESTKEYID00000000", "TESTSECRETTESTSECRETTESTSECRET0000"


def load_sample(symbols=None):
    index = json.loads((SAMPLE / "index.json").read_text())
    series = {}
    for e in index["entries"]:
        if symbols is None or e["s"] in symbols:
            series[e["s"]] = json.loads((SAMPLE / "series" / (e["s"] + ".json")).read_text())
    return index["entries"], series


class MockAlpaca:
    def __init__(self, symbols=None, iex_only=False, splits=None, page_size=None, rate_limit_first=0, require_auth=True, filler_assets=0):
        self.filler_assets = filler_assets
        self.entries, self.series = load_sample(symbols)
        self.iex_only, self.page_size, self.require_auth = iex_only, page_size, require_auth
        self.listed_scale = 1.0                       # scales ONLY the dividend amounts listed by corporate-actions (to simulate bad data)
        self.splits = splits or {}                    # {symbol: (ex_date, ratio)}; sample prices are the split-ADJUSTED truth
        self.rate_limit_left = rate_limit_first
        self.calls = []
        self.httpd = None

    # ---------- data shaping ----------
    def _factor_after(self, sym, date_str):
        """Product of split ratios whose ex-date is after date_str (raw price = adjusted price * this)."""
        f = 1.0
        if sym in self.splits and self.splits[sym][0] > date_str:
            f *= self.splits[sym][1]
        return f

    def bars_for(self, sym, start, end, adjustment, feed):
        s = self.series.get(sym)
        if not s:
            return []
        rows = []
        close_split = dict(zip(s["dates"], s["close"]))
        dates = s["dates"]
        for i, d in enumerate(dates):
            if not (start[:10] <= d <= end[:10]):
                continue
            c = close_split[d]
            if adjustment == "raw":
                c *= self._factor_after(sym, d)
            elif adjustment == "all":
                for ex, amt in (s["dividends"] or []):
                    if ex > d and ex in close_split:
                        j = dates.index(ex)
                        if j > 0:
                            c *= 1 - amt / close_split[dates[j - 1]]
            v = s["volume"][i]
            if feed == "iex":
                v = int(v * 0.03)
            rows.append({"t": d + "T05:00:00Z", "o": c, "h": c, "l": c, "c": round(c, 6), "v": v, "n": 1, "vw": c})
        return rows

    def actions_for(self, sym):
        s = self.series.get(sym)
        divs, splits = [], []
        if s and s["dividends"]:
            for ex, amt in s["dividends"]:
                divs.append({"id": f"{sym}-{ex}", "symbol": sym, "cusip": "X", "rate": round(amt * self._factor_after(sym, ex) * self.listed_scale, 6),
                             "special": False, "foreign": False, "ex_date": ex, "process_date": ex})
        if sym in self.splits:
            ex, ratio = self.splits[sym]
            splits.append({"id": f"{sym}-split", "symbol": sym, "cusip": "X", "ex_date": ex, "process_date": ex,
                           "old_rate": 1, "new_rate": ratio})
        return divs, splits

    # ---------- HTTP ----------
    def start(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, obj, headers=None):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urlsplit(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                outer.calls.append((u.path, q, dict(self.headers)))
                if outer.require_auth and (self.headers.get("APCA-API-KEY-ID") != KEY_ID or self.headers.get("APCA-API-SECRET-KEY") != SECRET):
                    return self._send(401, {"message": "forbidden."})
                if outer.rate_limit_left > 0:
                    outer.rate_limit_left -= 1
                    return self._send(429, {"message": "too many requests"}, {"X-RateLimit-Reset": str(int(time.time()) + 1)})
                if u.path == "/v2/account":
                    return self._send(200, {"status": "ACTIVE", "currency": "USD"})
                if u.path == "/v2/assets":
                    return self._send(200, [{"id": e["s"], "class": "us_equity", "exchange": e["x"].upper().replace(" ", ""), "symbol": e["s"],
                                             "name": e["n"], "status": "active", "tradable": True} for e in outer.entries]
                                      + [{"id": "x", "class": "us_equity", "exchange": "NYSE", "symbol": "ZZZ", "name": "Delisted Co", "status": "active", "tradable": False}]
                                      + [{"id": f"f{i}", "class": "us_equity", "exchange": "NYSE", "symbol": f"FIL{i}", "name": f"Filler Corporation {i}", "status": "active", "tradable": True} for i in range(outer.filler_assets)])
                if u.path == "/v2/stocks/bars":
                    feed = q.get("feed", "sip")
                    if feed == "sip" and outer.iex_only:
                        return self._send(403, {"code": 42210000, "message": "subscription does not permit querying recent SIP data"})
                    syms = [s for s in q.get("symbols", "").split(",") if s]
                    flat = []
                    for s in syms:
                        for b in outer.bars_for(s, q.get("start", "0000-00-00"), q.get("end", "9999-12-31"), q.get("adjustment", "raw"), feed):
                            flat.append((s, b))
                    limit = min(int(q.get("limit", 1000)), outer.page_size or 10000)
                    off = int(q.get("page_token") or 0)
                    page = flat[off:off + limit]
                    out = {}
                    for s, b in page:
                        out.setdefault(s, []).append(b)
                    nxt = str(off + limit) if off + limit < len(flat) else None
                    return self._send(200, {"bars": out, "next_page_token": nxt})
                if u.path == "/v1/corporate-actions":
                    syms = [s for s in q.get("symbols", "").split(",") if s]
                    flat = []
                    for s in syms:
                        divs, splits = outer.actions_for(s)
                        flat += [("cash_dividends", d) for d in divs] + [("forward_splits", d) for d in splits]
                    flat = [(k, d) for k, d in flat if q.get("start", "0000-00-00") <= d["process_date"] <= q.get("end", "9999-12-31")]
                    limit = min(int(q.get("limit", 100)), outer.page_size or 1000)
                    off = int(q.get("page_token") or 0)
                    out = {}
                    for k, d in flat[off:off + limit]:
                        out.setdefault(k, []).append(d)
                    nxt = str(off + limit) if off + limit < len(flat) else None
                    return self._send(200, {"corporate_actions": out, "next_page_token": nxt})
                return self._send(404, {"message": "not found"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
