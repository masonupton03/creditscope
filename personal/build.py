"""Turn Alpaca responses into the series files the Explorer reads (same format as explorer/sample).

Series: {symbol, name, type, exchange, currency, synthetic:false, dates, close, volume, dividends, feed}
  close      split-adjusted close (adjustment=split), NOT adjusted for dividends
  dividends  [[ex-date, cash per share on the SAME split-adjusted basis]] or null if unknown ([] = known, none paid)
  splits     [[ex-date, ratio]] (forward 4-for-1 = 4); the portfolio dashboard uses them to convert historical share counts

Dividend amounts from the corporate-actions endpoint are per-share amounts as declared at the time. Because the closes are
split-adjusted backwards, each dividend is divided by the product of the split ratios that happen AFTER its ex-date
(forward 4-for-1 = ratio 4; reverse 1-for-10 = ratio 0.1). Whether Alpaca already adjusts dividend rates is not stated in its
documentation, so `python -m personal doctor --verify-dividends` cross-checks this against Alpaca's own dividend-adjusted bars.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import config
from .alpaca import Client

ETF_NAME = re.compile(r"\b(ETF|ETN|ETP|Exchange[- ]Traded)\b|^(iShares|SPDR|Vanguard|Invesco|ProShares|Direxion|WisdomTree|"
                      r"Global X|VanEck|First Trust|Schwab (U\.?S\.?|International)|JPMorgan .*ETF|Select Sector)", re.I)


def guess_type(name: str) -> str:
    """'E' (ETF/ETN/ETP) or 'S' (stock). Alpaca does not flag ETFs, so this is a NAME-based guess."""
    return "E" if ETF_NAME.search(name or "") else "S"


def bar_date(bar: dict) -> str:
    return str(bar["t"])[:10]                                  # daily bars are stamped at ET midnight = 04:00/05:00 UTC


def adjusted_dividends(dividends: list, splits: list) -> list:
    """[[ex_date, amount]] on the split-adjusted basis, sorted, de-duplicated by (ex_date, amount)."""
    out = {}
    for d in dividends:
        ex, rate = d.get("ex_date"), d.get("rate")
        if not ex or rate is None:
            continue
        factor = 1.0
        for s in splits:
            if s.get("ex_date") and s["ex_date"] > ex:
                factor *= s["ratio"]
        out[(ex, round(float(rate) / factor, 6))] = None
    return [[ex, amt] for ex, amt in sorted(out)]


def make_series(symbol: str, bars: list, dividends: Optional[list], splits: list, meta: dict) -> Optional[dict]:
    rows = {}
    for b in bars:
        try:
            rows[bar_date(b)] = (float(b["c"]), int(b.get("v") or 0))
        except (KeyError, TypeError, ValueError):
            continue
    if len(rows) < 2:
        return None
    dates = sorted(rows)
    return {
        "symbol": symbol, "name": meta.get("name", symbol), "type": "ETF" if meta.get("t") == "E" else "Stock",
        "exchange": meta.get("exchange", ""), "currency": "USD", "synthetic": False, "feed": meta.get("feed", ""),
        "dates": dates, "close": [rows[d][0] for d in dates], "volume": [rows[d][1] for d in dates],
        "dividends": None if dividends is None else adjusted_dividends(dividends, splits),
        "splits": [list(x) for x in sorted({(sp["ex_date"], float(sp["ratio"])) for sp in splits if sp.get("ex_date") and sp.get("ratio")})] if splits is not None else None,
    }


def merge_series(old: dict, new: dict) -> dict:
    """Overlay `new` rows onto `old` by date; dividends are unioned."""
    rows = {d: (c, v) for d, c, v in zip(old["dates"], old["close"], old["volume"])}
    rows.update({d: (c, v) for d, c, v in zip(new["dates"], new["close"], new["volume"])})
    dates = sorted(rows)
    merged = dict(new)
    if old.get("splits") is not None and new.get("splits") is not None:
        merged["splits"] = [list(x) for x in sorted({tuple(x) for x in old["splits"] + new["splits"]})]
    merged.update({"dates": dates, "close": [rows[d][0] for d in dates], "volume": [rows[d][1] for d in dates]})
    if new["dividends"] is None or old["dividends"] is None:
        merged["dividends"] = new["dividends"] if new["dividends"] is not None else old["dividends"]
    else:
        merged["dividends"] = sorted({(a, b) for a, b in (tuple(x) for x in old["dividends"] + new["dividends"])})
        merged["dividends"] = [list(x) for x in merged["dividends"]]
    return merged


def atomic_write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def series_path(data: Path, symbol: str) -> Path:
    return data / "series" / (symbol + ".json")


def read_series(data: Path, symbol: str) -> Optional[dict]:
    try:
        return json.loads(series_path(data, symbol).read_text())
    except (OSError, ValueError):
        return None


def build_index(assets: list, universe: list, feed: str, as_of: str, synced: list) -> dict:
    rank = {s: i + 1 for i, s in enumerate(universe)}
    entries = []
    for a in assets:
        sym = a.get("symbol")
        if not sym or not a.get("tradable", True) or not re.match(config.SYMBOL_RE, sym):
            continue
        e = {"s": sym, "n": a.get("name", sym), "t": guess_type(a.get("name", "")), "x": a.get("exchange", "")}
        if sym in rank:
            e["r"] = rank[sym]
        entries.append(e)
    entries.sort(key=lambda e: (e.get("r", 10**9), e["s"]))
    meta = {"synthetic": False, "private": True, "provider": "Alpaca (personal, private use only)", "feed": feed,
            "asOf": as_of, "count": len(entries), "synced": sorted(synced), "benchmark": config.BENCHMARK,
            "priceBasis": "split-adjusted close, not dividend-adjusted",
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    return {"meta": meta, "entries": entries}


def date_window(years: int, today: Optional[date] = None) -> tuple:
    """(start, end): end = yesterday (a complete trading day; keeps clear of Basic's recent-data restriction)."""
    today = today or config.today()
    end = today - timedelta(days=1)
    return (end.replace(year=end.year - years) - timedelta(days=7)).isoformat(), end.isoformat()


def sync_symbols(client: Client, symbols: list, data: Path, feed: str, names: dict, years: int = config.HISTORY_YEARS,
                 today: Optional[date] = None, chunk: int = 20, log=lambda m: None) -> dict:
    """Download history for `symbols` and write series files. Returns {'written': [...], 'skipped': {sym: reason}}."""
    start, end = date_window(years, today)
    written, skipped = [], {}
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        log(f"downloading {', '.join(batch)}")
        bars = client.bars(batch, start, end, adjustment="split", feed=feed)
        actions = client.corporate_actions(batch, start, (date.fromisoformat(end) + timedelta(days=45)).isoformat())
        for sym in batch:
            meta = dict(names.get(sym, {}), feed=feed)
            series = make_series(sym, bars.get(sym, []), actions["dividends"].get(sym, []), actions["splits"].get(sym, []), meta)
            if series is None:
                skipped[sym] = "no usable bars returned"
                continue
            atomic_write(series_path(data, sym), series)
            written.append(sym)
    return {"written": written, "skipped": skipped}
