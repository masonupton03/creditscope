"""Generate the SIMULATED sample dataset for the Stock Explorer (explorer/sample/).

These prices are NOT real market data. They are generated from a seeded random model so that the
Explorer can be demonstrated, tested and developed without any data licence. Real tickers and names
are used only so searching feels natural; every series carries "synthetic": true and the page shows
a permanent notice.

The model: one shared market factor (with a 2022-style bear market and a 2025 correction), a beta and
idiosyncratic noise per security, bonds that fall during the 2022 "rate shock", quarterly or monthly
dividends paid on ex-dates (the price drops by the dividend), and volume that rises on big moves.
Dividend history is deliberately "known" for some securities, "known: none paid" for others and
"unknown" (null) for the rest, so that every labelling state of the UI can be exercised.

    python scripts/make_explorer_sample.py            # writes explorer/sample/{index.json,series/*.json}
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "explorer" / "sample"
START, END = date(2021, 11, 15), date(2026, 11, 13)
MARKET_VOL = 0.0105          # daily vol of the market factor (about 16.7% a year)

# sym: (name, type S/E, exchange, rank, mu%, vol%, beta, dividend: None | 0 | (yield, 'Q'|'M', month offset), start price, base volume, first date)
U = {
    "SPY":  ("SPDR S&P 500 ETF Trust", "E", "NYSE Arca", 1, 9.0, 16.5, 1.00, (0.013, "Q", 0), 450.0, 70e6, None),
    "QQQ":  ("Invesco QQQ Trust", "E", "Nasdaq", 2, 12.0, 21.0, 1.25, (0.006, "Q", 0), 390.0, 45e6, None),
    "IWM":  ("iShares Russell 2000 ETF", "E", "NYSE Arca", 8, 6.0, 22.0, 1.15, None, 230.0, 30e6, None),
    "EFA":  ("iShares MSCI EAFE ETF", "E", "NYSE Arca", 9, 5.0, 16.0, 0.85, (0.030, "Q", 1), 80.0, 18e6, None),
    "EEM":  ("iShares MSCI Emerging Markets ETF", "E", "NYSE Arca", 10, 3.5, 18.0, 0.80, None, 50.0, 28e6, None),
    "XLF":  ("Financial Select Sector SPDR Fund", "E", "NYSE Arca", 11, 8.0, 19.0, 1.10, (0.016, "Q", 2), 40.0, 40e6, None),
    "VTI":  ("Vanguard Total Stock Market ETF", "E", "NYSE Arca", 5, 9.0, 16.5, 1.00, (0.014, "Q", 0), 235.0, 4e6, None),
    "GLD":  ("SPDR Gold Shares", "E", "NYSE Arca", 7, 6.0, 14.0, 0.05, None, 170.0, 9e6, None),
    "SHY":  ("iShares 1-3 Year Treasury Bond ETF", "E", "Nasdaq", 20, 2.0, 1.8, 0.00, (0.030, "M", 0), 84.0, 3e6, None),
    "IEF":  ("iShares 7-10 Year Treasury Bond ETF", "E", "Nasdaq", 14, 1.0, 6.5, 0.05, (0.028, "M", 0), 108.0, 8e6, None),
    "TLT":  ("iShares 20+ Year Treasury Bond ETF", "E", "Nasdaq", 6, 0.0, 14.0, 0.05, (0.036, "M", 0), 130.0, 30e6, None),
    "AGG":  ("iShares Core U.S. Aggregate Bond ETF", "E", "NYSE Arca", 12, 1.2, 5.5, 0.05, None, 115.0, 9e6, None),
    "LQD":  ("iShares iBoxx $ Investment Grade Corporate Bond ETF", "E", "NYSE Arca", 15, 2.0, 8.0, 0.20, (0.040, "M", 0), 128.0, 18e6, None),
    "HYG":  ("iShares iBoxx $ High Yield Corporate Bond ETF", "E", "NYSE Arca", 13, 3.0, 7.5, 0.35, (0.059, "M", 0), 86.0, 32e6, None),
    "AAPL": ("Apple Inc.", "S", "Nasdaq", 3, 16.0, 28.0, 1.20, (0.005, "Q", 1), 150.0, 60e6, None),
    "MSFT": ("Microsoft Corporation", "S", "Nasdaq", 4, 16.0, 27.0, 1.15, (0.008, "Q", 2), 330.0, 25e6, None),
    "NVDA": ("NVIDIA Corporation", "S", "Nasdaq", 16, 28.0, 52.0, 1.45, (0.001, "Q", 0), 30.0, 280e6, None),
    "AMZN": ("Amazon.com, Inc.", "S", "Nasdaq", 17, 12.0, 32.0, 1.30, 0, 175.0, 45e6, None),
    "GOOGL": ("Alphabet Inc. Class A", "S", "Nasdaq", 18, 15.0, 30.0, 1.15, 0, 140.0, 28e6, None),
    "META": ("Meta Platforms, Inc.", "S", "Nasdaq", 19, 17.0, 40.0, 1.35, 0, 330.0, 15e6, None),
    "TSLA": ("Tesla, Inc.", "S", "Nasdaq", 21, 6.0, 58.0, 1.45, 0, 330.0, 90e6, None),
    "NFLX": ("Netflix, Inc.", "S", "Nasdaq", 22, 13.0, 42.0, 1.20, 0, 600.0, 5e6, None),
    "RDDT": ("Reddit, Inc. Class A", "S", "NYSE", 40, 8.0, 70.0, 1.30, 0, 47.0, 9e6, date(2024, 3, 21)),
    "JPM":  ("JPMorgan Chase & Co.", "S", "NYSE", 23, 11.0, 24.0, 1.10, (0.022, "Q", 1), 160.0, 9e6, None),
    "KO":   ("The Coca-Cola Company", "S", "NYSE", 24, 6.0, 15.0, 0.45, None, 60.0, 14e6, None),
    "JNJ":  ("Johnson & Johnson", "S", "NYSE", 25, 4.0, 15.0, 0.45, None, 170.0, 7e6, None),
    "XOM":  ("Exxon Mobil Corporation", "S", "NYSE", 26, 12.0, 27.0, 0.90, (0.035, "Q", 2), 70.0, 17e6, None),
    "PG":   ("The Procter & Gamble Company", "S", "NYSE", 27, 6.0, 15.0, 0.50, (0.024, "Q", 1), 145.0, 7e6, None),
    "V":    ("Visa Inc. Class A", "S", "NYSE", 28, 11.0, 22.0, 1.00, (0.008, "Q", 0), 225.0, 7e6, None),
    "WMT":  ("Walmart Inc.", "S", "NYSE", 29, 11.0, 20.0, 0.55, (0.012, "Q", 2), 55.0, 20e6, None),
}


def nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def last_monday(year, month):
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - 0) % 7)


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def observed(d):
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def holidays(year):
    return {observed(date(year, 1, 1)), nth_weekday(year, 1, 0, 3), nth_weekday(year, 2, 0, 3),
            easter(year) - timedelta(days=2), last_monday(year, 5), observed(date(year, 6, 19)),
            observed(date(year, 7, 4)), nth_weekday(year, 9, 0, 1), nth_weekday(year, 11, 3, 4),
            observed(date(year, 12, 25))}


def trading_days():
    hol = set()
    for y in range(START.year, END.year + 1):
        hol |= holidays(y)
    days, d = [], START
    while d <= END:
        if d.weekday() < 5 and d not in hol:
            days.append(d)
        d += timedelta(days=1)
    return days


def regime(d):
    """Extra daily drift of the market factor: 2022-style bear market, recovery, 2025 correction."""
    if date(2022, 1, 3) <= d <= date(2022, 10, 12):
        return -0.0010
    if date(2022, 10, 13) <= d <= date(2023, 12, 29):
        return 0.0007
    if date(2025, 2, 19) <= d <= date(2025, 4, 8):
        return -0.0016
    if date(2025, 4, 9) <= d <= date(2025, 9, 30):
        return 0.0012
    return 0.0

def bond_shock(d):
    return -0.0007 if date(2022, 1, 3) <= d <= date(2022, 10, 24) else 0.0


def ex_dates(days, spec):
    """Monthly payers go ex on the first trading day of each month; quarterly payers on the first
    trading day on/after the 15th of their quarter months (offset 0 = Jan/Apr/Jul/Oct, 1 = Feb/..., 2 = Mar/...)."""
    freq, offset = spec[1], spec[2]
    out, seen = set(), set()
    for d in days:
        key = (d.year, d.month)
        if key in seen:
            continue
        if freq == "M" or ((d.month - 1) % 3 == offset and d.day >= 15):
            seen.add(key)
            out.add(d)
    return out


def simulate():
    days = trading_days()
    rng_m = random.Random("market:2026")
    market = [regime(d) + MARKET_VOL * rng_m.gauss(0, 1) for d in days]
    index_entries, series_out = [], {}
    for sym, (name, typ, exch, rank, mu, vol, beta, div, p0, v0, first) in U.items():
        rng = random.Random("sym:" + sym)
        sig_idio = math.sqrt(max((vol / 100) ** 2 - (beta * MARKET_VOL * math.sqrt(252)) ** 2, (0.2 * vol / 100) ** 2)) / math.sqrt(252)
        is_bond = sym in ("SHY", "IEF", "TLT", "AGG", "LQD", "HYG")
        exd = ex_dates(days, div) if isinstance(div, tuple) else set()
        dates, close, volume, dividends = [], [], [], []
        price, ref_price = p0, p0
        for k, d in enumerate(days):
            if first and d < first:
                continue
            r = mu / 100 / 252 + beta * market[k] + sig_idio * rng.gauss(0, 1) + (bond_shock(d) * (1.0 if sym != "SHY" else 0.15) if is_bond else 0.0)
            if not dates:
                price_t = price                                   # first row is the starting price
                cash = 0.0
            else:
                gross = price * (1 + r)
                cash = 0.0
                if d in exd:
                    per_year = 12 if div[1] == "M" else 4
                    cash = round(div[0] * ref_price / per_year, 4)
                    ref_price = price
                price_t = max(gross - cash, 0.5)
            if not dates:
                ref_price = price_t
            dates.append(d.isoformat())
            close.append(round(price_t, 2))
            price = price_t
            volume.append(int(v0 * rng.lognormvariate(0, 0.25) * (1 + 10 * abs(r))))
            if cash:
                dividends.append([d.isoformat(), cash])
        div_field = None if div is None else dividends          # None = unknown, [] = known none, else payments
        series_out[sym] = {"symbol": sym, "name": name, "type": "ETF" if typ == "E" else "Stock", "exchange": exch,
                           "currency": "USD", "synthetic": True, "dates": dates, "close": close, "volume": volume,
                           "dividends": div_field, "splits": []}
        index_entries.append({"s": sym, "n": name, "t": typ, "x": exch, "r": rank})
    index_entries.sort(key=lambda e: (e["r"], e["s"]))
    meta = {"synthetic": True, "provider": "Simulated sample data (not real market prices)", "asOf": END.isoformat(),
            "count": len(index_entries), "benchmark": "SPY", "priceBasis": "split-adjusted close, not dividend-adjusted"}
    return {"meta": meta, "entries": index_entries}, series_out


def write(out: Path = OUT):
    (out / "series").mkdir(parents=True, exist_ok=True)
    index, series = simulate()
    dump = lambda o: json.dumps(o, separators=(",", ":"))
    (out / "index.json").write_text(dump(index) + "\n")
    for sym, s in series.items():
        (out / "series" / (sym + ".json")).write_text(dump(s) + "\n")
    return index, series


if __name__ == "__main__":
    idx, ser = write()
    total = sum(len(v["dates"]) for v in ser.values())
    print("wrote %d series (%d rows) to %s" % (len(ser), total, OUT))
