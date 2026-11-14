"""Orchestration: detect what the account can access, sync the universe, fetch single symbols on demand."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import build, config
from .alpaca import AlpacaError, Client

SYMBOL = re.compile(config.SYMBOL_RE)
STALE_AFTER = timedelta(hours=20)


def detect_feed(client: Client, today: Optional[date] = None) -> tuple:
    """('sip'|'iex', note). Consolidated SIP history older than 15 minutes is listed for the Basic plan, but a Paper Only
    account is described as IEX-only, so ask Alpaca instead of assuming."""
    today = today or config.today()
    start = (today - timedelta(days=12)).isoformat()
    end = (today - timedelta(days=5)).isoformat()
    try:
        data = client.bars(["SPY"], start, end, adjustment="split", feed="sip")
        if data.get("SPY"):
            return "sip", "Consolidated (SIP) daily bars are available."
    except AlpacaError as e:
        if e.status not in (403, 422):
            raise
    data = client.bars(["SPY"], start, end, adjustment="split", feed="iex")
    if not data.get("SPY"):
        raise AlpacaError("Alpaca returned no recent bars for SPY on either feed; check the keys and the market-data permissions.")
    return "iex", ("Only the IEX feed is available: prices come from IEX trades and volume is IEX-only "
                   "(a small share of total market volume), so volume and some closes will differ from consolidated data.")


def asset_names(assets: list) -> dict:
    return {a["symbol"]: {"name": a.get("name", a["symbol"]), "t": build.guess_type(a.get("name", "")), "exchange": a.get("exchange", "")}
            for a in assets if a.get("symbol")}


def full_sync(client: Client, symbols: list, data: Path, log=lambda m: None, years: int = config.HISTORY_YEARS) -> dict:
    assets = client.assets()
    feed, note = detect_feed(client)
    log(note)
    names = asset_names(assets)
    result = build.sync_symbols(client, symbols, data, feed, names, years=years, log=log)
    as_of = ""
    for sym in result["written"]:
        s = build.read_series(data, sym)
        if s:
            as_of = max(as_of, s["dates"][-1])
    index = build.build_index(assets, symbols, feed, as_of, result["written"])
    build.atomic_write(data / "index.json", index)
    result.update({"feed": feed, "feed_note": note, "assets": len(index["entries"]), "as_of": as_of})
    return result


def cached_series(data: Path, symbol: str, max_age: timedelta = STALE_AFTER) -> Optional[dict]:
    path = build.series_path(data, symbol)
    try:
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None
    return build.read_series(data, symbol) if age <= max_age else None


def fetch_symbol(client: Client, symbol: str, data: Path, feed: str, log=lambda m: None) -> Optional[dict]:
    """Download one symbol that is not in the synced universe (used by the local server on demand)."""
    if not SYMBOL.match(symbol):
        raise ValueError("invalid symbol")
    try:
        assets = client.assets()
        names = asset_names(assets)
    except AlpacaError:
        names = {}
    build.sync_symbols(client, [symbol], data, feed, names, log=log)
    return build.read_series(data, symbol)


def verify_dividends(client: Client, symbol: str, start: str, end: str, feed: str) -> list:
    """Cross-check the split-adjusted dividend amounts against Alpaca's own dividend-adjusted bars.

    Alpaca's adjustment=all close divided by its adjustment=split close is a cumulative dividend factor f_t. Adjusted prices are
    scaled BACKWARDS, so f rises across an ex-date: f_prev / f_ex = 1 - D / P_prev. The implied dividend is therefore
    D = P_prev * (1 - f_prev / f_ex), and it should match the listed, split-adjusted amount. Returns one record per dividend
    whose ex-date falls inside the window."""
    split = client.bars([symbol], start, end, adjustment="split", feed=feed).get(symbol, [])
    allb = client.bars([symbol], start, end, adjustment="all", feed=feed).get(symbol, [])
    actions = client.corporate_actions([symbol], start, end)
    divs = build.adjusted_dividends(actions["dividends"].get(symbol, []), actions["splits"].get(symbol, []))
    sp = {build.bar_date(b): float(b["c"]) for b in split}
    al = {build.bar_date(b): float(b["c"]) for b in allb}
    dates = sorted(d for d in sp if d in al)
    factor = {d: al[d] / sp[d] for d in dates}
    out = []
    for ex, listed in divs:
        if ex not in factor:
            continue
        i = dates.index(ex)
        if i == 0:
            continue
        prev = dates[i - 1]
        implied = sp[prev] * (1 - factor[prev] / factor[ex])
        out.append({"ex_date": ex, "listed": listed, "implied": round(implied, 6),
                    "ok": abs(implied - listed) <= max(0.01, 0.05 * listed)})
    return out
