"""Conversion of the raw Nasdaq response to the common columns, incl. missing values."""
import json

import pytest

from creditscope.config import COLUMNS
from creditscope.convert import ConvertError, clean_number, convert, convert_nasdaq, parse_market_date
from conftest import FIXTURES, nasdaq_response


def test_real_response_converts_to_common_columns():
    raw = (FIXTURES / "nasdaq-SPY.json").read_bytes()
    (row,) = convert_nasdaq("2026-11-14", "nasdaq-SPY", raw)
    assert list(row) == COLUMNS
    assert row["date"] == "2026-11-14"           # collection date, not market date
    assert row["item_id"] == "SPY"
    assert row["item"] == "State Street SPDR S&P 500 ETF Trust"
    assert row["source"] == "nasdaq-SPY"
    assert (row["asset_class"], row["category"]) == ("Stock", "US large cap")
    assert row["price"] == "754.21"
    assert row["volume"] == "38720038"
    assert row["net_change"] == "-2.91"
    assert row["pct_change"] == "-0.38"
    assert row["price_date"] == "2026-11-13"
    assert row["market_status"] == "Closed"


def test_dispatch_by_provider_and_unknown_provider():
    assert convert("nasdaq", "2026-11-14", "nasdaq-SPY", nasdaq_response())[0]["item_id"] == "SPY"
    with pytest.raises(ConvertError):
        convert("bogus", "2026-11-14", "bogus-SPY", b"{}")


@pytest.mark.parametrize("text,expected", [
    ("$754.21", "754.21"), ("38,720,038", "38720038"), ("-0.38%", "-0.38"), ("+1.5", "1.5"),
    ("N/A", ""), ("", ""), (None, ""), ("--", ""), ("abc", ""), ("  12.5 ", "12.5"), (0, "0"),
])
def test_clean_number(text, expected):
    assert clean_number(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Nov 13, 2026", "2026-11-13"),
    ("Nov 3, 2026", "2026-11-03"),
    ("Last trade as of Dec 1, 2026 4:00 PM ET", "2026-12-01"),
    ("N/A", ""), ("", ""), (None, ""), ("Xyz 13, 2026", ""),
])
def test_parse_market_date(text, expected):
    assert parse_market_date(text) == expected


def test_missing_volume_and_changes_become_empty_not_failure():
    raw = nasdaq_response(volume="N/A", net="N/A", pct="", stamp="N/A")
    (row,) = convert_nasdaq("2026-11-14", "nasdaq-SPY", raw)
    assert row["price"] == "100.00"
    assert row["volume"] == "" and row["net_change"] == "" and row["pct_change"] == ""
    assert row["price_date"] == ""


def test_missing_price_is_a_conversion_failure():
    with pytest.raises(ConvertError, match="no price"):
        convert_nasdaq("2026-11-14", "nasdaq-SPY", nasdaq_response(price="N/A"))


@pytest.mark.parametrize("raw", [
    b"", b"not json", b"<html>Access denied</html>", b"[]", b"null",
    json.dumps({"data": None, "status": {"rCode": 400}}).encode(),
    json.dumps({"data": {"symbol": "SPY", "primaryData": None}}).encode(),
])
def test_unusable_responses_raise(raw):
    with pytest.raises(ConvertError):
        convert_nasdaq("2026-11-14", "nasdaq-SPY", raw)


def test_unexpected_symbol_rejected():
    with pytest.raises(ConvertError, match="unexpected symbol"):
        convert_nasdaq("2026-11-14", "nasdaq-ZZZ", nasdaq_response(symbol="ZZZ"))
