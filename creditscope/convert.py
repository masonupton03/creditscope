"""Convert one raw source response into rows with the common columns."""
from __future__ import annotations

import json
import re

from .config import ETF_INFO

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


class ConvertError(ValueError):
    """The raw response is not usable."""


def clean_number(value) -> str:
    """'$754.21' -> '754.21', '38,720,038' -> '38720038', '-0.38%' -> '-0.38'.

    Missing values ('N/A', '', None, '--') become the empty string.
    """
    if value is None:
        return ""
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "").replace("+", "")
    if text in ("", "N/A", "--", "-", "n/a"):
        return ""
    try:
        float(text)
    except ValueError:
        return ""
    return text


def parse_market_date(value) -> str:
    """'Nov 13, 2026' (or text containing it) -> '2026-11-13'. Empty if not found."""
    m = re.search(r"([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}), (\d{4})", str(value or ""))
    if not m or m.group(1) not in MONTHS:
        return ""
    return f"{int(m.group(3)):04d}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


def convert_nasdaq(date: str, source: str, raw: bytes) -> list:
    """Nasdaq quote JSON for one ETF -> one history row (as a list of one dict)."""
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ConvertError(f"{source}: not valid JSON") from exc
    data = (doc or {}).get("data") if isinstance(doc, dict) else None
    if not data or not data.get("primaryData"):
        raise ConvertError(f"{source}: response has no quote data")
    symbol = str(data.get("symbol", "")).upper()
    if symbol not in ETF_INFO:
        raise ConvertError(f"{source}: unexpected symbol {symbol!r}")
    p = data["primaryData"]
    price = clean_number(p.get("lastSalePrice"))
    if not price:
        raise ConvertError(f"{source}: no price reported")
    info = ETF_INFO[symbol]
    return [{
        "date": date,
        "item_id": symbol,
        "item": str(data.get("companyName") or symbol).strip(),
        "source": source,
        "asset_class": info["asset_class"],
        "category": info["category"],
        "price": price,
        "volume": clean_number(p.get("volume")),
        "net_change": clean_number(p.get("netChange")),
        "pct_change": clean_number(p.get("percentageChange")),
        "price_date": parse_market_date(p.get("lastTradeTimestamp")),
        "market_status": str(data.get("marketStatus") or "").strip(),
    }]


CONVERTERS = {"nasdaq": convert_nasdaq}


def convert(provider: str, date: str, source: str, raw: bytes) -> list:
    if provider not in CONVERTERS:
        raise ConvertError(f"unknown provider {provider!r}")
    return CONVERTERS[provider](date, source, raw)
