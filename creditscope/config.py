"""Configuration: the tracked ETFs, the sources, and the history columns."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# item_id, asset_class, category
ETFS = [
    ("SPY", "Stock", "US large cap"),
    ("QQQ", "Stock", "US growth"),
    ("IWM", "Stock", "US small cap"),
    ("EFA", "Stock", "Developed international"),
    ("EEM", "Stock", "Emerging markets"),
    ("XLF", "Stock", "Financials"),
    ("SHY", "Bond", "Short Treasury"),
    ("IEF", "Bond", "Intermediate Treasury"),
    ("TLT", "Bond", "Long Treasury"),
    ("AGG", "Bond", "Broad market"),
    ("LQD", "Bond", "Investment grade corporate"),
    ("HYG", "Bond", "High yield corporate"),
]
ETF_INFO = {sym: {"asset_class": a, "category": c} for sym, a, c in ETFS}

# Providers in priority order. When two providers report the same item on the
# same day, the build keeps the row from the earlier provider in this list.
PROVIDERS = ["nasdaq"]

# One source = one provider + one ETF. Source name = raw file name stem.
NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=etf"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# The first four columns are fixed by the assignment.
COLUMNS = [
    "date", "item_id", "item", "source",
    "asset_class", "category",
    "price", "volume", "net_change", "pct_change",
    "price_date", "market_status",
]
NUMERIC_COLUMNS = ["price", "volume", "net_change", "pct_change"]

RAW_DIR = "data/raw"
RUNS_DIR = "data/runs"
HISTORY_FILE = "data/history.csv"
STATUS_FILE = "data/status.json"

TOP_N_MOVERS = 5
