"""Shared helpers: synthetic Nasdaq responses and a temporary project root."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from creditscope.config import ETFS
from creditscope.sources import Source, all_sources

FIXTURES = Path(__file__).parent / "fixtures"


def load_template() -> dict:
    return json.loads((FIXTURES / "nasdaq-SPY.json").read_text())


def nasdaq_response(symbol="SPY", price="$100.00", volume="1,000", net="1.00", pct="1.00%",
                    stamp="Nov 13, 2026", name=None, status="Closed") -> bytes:
    """A Nasdaq-shaped quote response (built from a real saved response)."""
    doc = load_template()
    data = doc["data"]
    data["symbol"] = symbol
    data["companyName"] = name or f"{symbol} Test ETF"
    data["marketStatus"] = status
    p = data["primaryData"]
    p.update({"lastSalePrice": price, "volume": volume, "netChange": net,
              "percentageChange": pct, "lastTradeTimestamp": stamp})
    return json.dumps(doc).encode()


def at(day: str, hour: int = 21, minute: int = 45) -> datetime:
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=timezone.utc)


def make_fetcher(prices=None, fail=(), junk=()):
    """Fetcher keyed on the symbol in the URL. prices: symbol -> price string."""
    prices = prices or {}

    def fetch(url):
        symbol = url.split("/quote/")[1].split("/")[0]
        if symbol in fail:
            raise RuntimeError("simulated outage")
        if symbol in junk:
            return b"<html>blocked</html>"
        return nasdaq_response(symbol, price=prices.get(symbol, "$100.00"))
    return fetch


@pytest.fixture
def root(tmp_path):
    return tmp_path


@pytest.fixture
def symbols():
    return [s for s, _a, _c in ETFS]


@pytest.fixture
def sources():
    return all_sources()


def approx_equal(a, b, path="value", rel=1e-9):
    """Deep comparison of JSON-like values where floats may differ in the last digits."""
    import pytest as _pytest
    if isinstance(b, dict):
        assert isinstance(a, dict), path
        for k in b:
            assert k in a, f"{path}.{k} missing"
            approx_equal(a[k], b[k], f"{path}.{k}", rel)
    elif isinstance(b, list):
        assert isinstance(a, list) and len(a) == len(b), f"{path} length {len(a) if isinstance(a, list) else a} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            approx_equal(x, y, f"{path}[{i}]", rel)
    elif isinstance(b, float) or isinstance(a, float):
        assert a == _pytest.approx(b, rel=rel, abs=1e-12), path
    else:
        assert a == b, f"{path}: {a!r} vs {b!r}"
