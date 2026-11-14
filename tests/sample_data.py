"""Deterministic sample history for developing and testing the website.

It drives the real pipeline (raw files -> build -> status) with synthetic Nasdaq-shaped
responses covering weekends, a failed source and a day when every source failed, then
copies history.csv and status.json to an output folder.

    python tests/sample_data.py OUTDIR      # writes OUTDIR/data/history.csv and status.json
"""
from __future__ import annotations

import json
import random
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from creditscope.build import build  # noqa: E402
from creditscope.config import ETFS  # noqa: E402
from creditscope.raw import save_raw  # noqa: E402
from creditscope.status import build_status, write_status  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
START = date(2026, 11, 2)
DAYS = 15                      # 2026-11-02 .. 2026-11-16 collection days
START_PRICE = {"SPY": 750, "QQQ": 680, "IWM": 240, "EFA": 104, "EEM": 61, "XLF": 53,
               "SHY": 82, "IEF": 95, "TLT": 88, "AGG": 95, "LQD": 103, "HYG": 77}
VOL = {"Stock": 0.011, "Bond": 0.004}
BASE_VOLUME = {"SPY": 38e6, "QQQ": 42e6, "IWM": 28e6, "EFA": 9e6, "EEM": 27e6, "XLF": 40e6,
               "SHY": 3e6, "IEF": 8e6, "TLT": 30e6, "AGG": 11e6, "LQD": 18e6, "HYG": 34e6}
NAMES = {s: f"{s} Sample ETF" for s, _a, _c in ETFS}
FAILED_SOURCE = (date(2026, 11, 6), "TLT")     # one source down that day
ALL_FAILED_DAY = date(2026, 11, 10)            # every source down that day
MISSING_VOLUME = (date(2026, 11, 5), "EFA")    # source reports N/A volume


def response(symbol, price, volume, net, pct, stamp):
    doc = json.loads((FIXTURES / "nasdaq-SPY.json").read_text())
    d = doc["data"]
    d["symbol"], d["companyName"], d["marketStatus"] = symbol, NAMES[symbol], "Closed"
    d["primaryData"].update({
        "lastSalePrice": f"${price:.2f}", "volume": "N/A" if volume is None else f"{volume:,}",
        "netChange": f"{net:.2f}", "percentageChange": f"{pct:.2f}%", "lastTradeTimestamp": stamp})
    return json.dumps(doc).encode()


def last_session(day):
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def generate(root: Path) -> dict:
    rng = random.Random(2026)
    prev_close = dict(START_PRICE)
    last_stamp = None
    record = None
    for i in range(DAYS):
        day = START + timedelta(days=i)
        sess = last_session(day)
        new_session = sess != last_stamp
        last_stamp = sess
        for sym, cls, _cat in ETFS:
            if new_session:
                ret = rng.gauss(0.0002 if cls == "Stock" else 0.0001, VOL[cls])
                close = round(prev_close[sym] * (1 + ret), 2)
                net, pct = close - prev_close[sym], (close / prev_close[sym] - 1) * 100
                vol = int(BASE_VOLUME[sym] * rng.lognormvariate(0, 0.25))
                prev_close[sym] = close
                cache = (close, vol, net, pct)
                setattr(generate, "cache_" + sym, cache)
            close, vol, net, pct = getattr(generate, "cache_" + sym)
            if day == ALL_FAILED_DAY or (day, sym) == FAILED_SOURCE:
                continue
            if (sess, sym) == MISSING_VOLUME:
                vol = None
            stamp = f"{sess.strftime('%b')} {sess.day}, {sess.year}"
            save_raw(root, day.isoformat(), f"nasdaq-{sym}", "json", response(sym, close, vol, net, pct, stamp))
        if day != ALL_FAILED_DAY:
            failed = [f"nasdaq-{FAILED_SOURCE[1]}"] if day == FAILED_SOURCE[0] else []
            record = {"date": day.isoformat(),
                      "run_time": datetime(day.year, day.month, day.day, 21, 45, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "sources": [{"name": f"nasdaq-{s}", "ok": f"nasdaq-{s}" not in failed,
                                   "count": 0 if f"nasdaq-{s}" in failed else 1} for s, _a, _c in ETFS]}
    rows = build(root)
    status = build_status(root, record, rows)
    write_status(root, status)
    return status


def write_sample(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        (out / "data").mkdir(parents=True, exist_ok=True)
        for name in ("history.csv", "status.json"):
            shutil.copyfile(Path(tmp) / "data" / name, out / "data" / name)


if __name__ == "__main__":
    write_sample(Path(sys.argv[1]))
    print("sample data written to", sys.argv[1])
