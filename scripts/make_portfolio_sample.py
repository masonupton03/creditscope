"""Generate explorer/sample/portfolio.json: a SIMULATED demo portfolio built from the simulated sample series.

Trades are placed at that day's simulated close on real trading dates, so the numbers are internally consistent. Nothing here
is anyone's real holdings. Run:  python3 scripts/make_portfolio_sample.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERIES = ROOT / "explorer" / "sample" / "series"
OUT = ROOT / "explorer" / "sample" / "portfolio.json"


def close_on(sym, date):
    s = json.loads((SERIES / f"{sym}.json").read_text())
    i = next(k for k, d in enumerate(s["dates"]) if d >= date)
    return s["dates"][i], s["close"][i]


PLAN = [  # (date, type, symbol, shares, amount, note)
    ("2022-03-01", "deposit", None, None, 25000.0, "Initial funding"),
    ("2022-03-02", "buy", "VTI", 60, None, "Core US equity"),
    ("2022-03-02", "buy", "AAPL", 25, None, ""),
    ("2022-03-02", "buy", "TLT", 40, None, "Duration"),
    ("2022-09-15", "deposit", None, None, 6000.0, "Top-up"),
    ("2022-09-16", "buy", "MSFT", 18, None, ""),
    ("2023-03-01", "deposit", None, None, 8000.0, "Annual contribution"),
    ("2023-04-03", "buy", "XOM", 45, None, ""),
    ("2023-12-01", "deposit", None, None, 4000.0, "Year-end contribution"),
    ("2023-12-04", "buy", "VTI", 12, None, ""),
    ("2024-06-03", "sell", "AAPL", 10, None, "Trim"),
    ("2024-11-01", "withdrawal", None, None, 3000.0, "Spending"),
    ("2025-02-03", "fee", None, None, 15.0, "Account fee"),
    ("2025-05-01", "deposit", None, None, 5000.0, ""),
    ("2025-05-02", "buy", "NVDA", 20, None, ""),
]


def main():
    txs = []
    for n, (date, kind, sym, shares, amount, note) in enumerate(PLAN, 1):
        t = {"id": f"d{n}", "date": date, "type": kind}
        if sym:
            d, px = close_on(sym, date)
            t.update(date=d, symbol=sym, shares=shares, price=px, fee=0)
        else:
            t["amount"] = amount
        if note:
            t["note"] = note
        txs.append(t)
    txs.sort(key=lambda t: t["date"])
    OUT.write_text(json.dumps({"version": 1, "baseCurrency": "USD", "benchmark": "SPY", "synthetic": True, "transactions": txs},
                              separators=(",", ":")) + "\n")
    print("wrote", OUT, len(txs), "transactions")


if __name__ == "__main__":
    main()
