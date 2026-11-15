"""Comparison tool: JavaScript engine vs the independent Python reference on the simulated sample series, plus edge cases."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import ref_compare as ref  # noqa: E402

NODE = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")
load = lambda *syms: [json.loads((ROOT / "explorer/sample/series" / f"{s}.json").read_text()) for s in syms]
PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "MAX"]


def run_js(cases):
    f = ROOT / "tests" / "_cmp_cases.json"
    try:
        f.write_text(json.dumps({"cases": cases}))
        return json.loads(subprocess.run([NODE, str(ROOT / "tests/js/crosscheck_compare.js"), str(f)], capture_output=True, text=True, check=True).stdout)
    finally:
        f.unlink(missing_ok=True)


def close(a, b, msg):
    if a is None or b is None:
        assert a == b, msg
    else:
        assert abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b)), f"{msg}: {a} vs {b}"


GROUPS = {"known_dividends": ["AAPL", "MSFT", "TLT", "XOM"], "has_unknown_dividends": ["AAPL", "KO", "GLD"], "short_history": ["AAPL", "RDDT", "NVDA"], "two": ["QQQ", "AGG"]}


@pytest.mark.parametrize("group", list(GROUPS))
def test_js_matches_reference_for_every_period(group):
    spy = load("SPY")[0]
    series = load(*GROUPS[group])
    cases = [{"list": series, "period": p, "benchmark": spy} for p in PERIODS]
    for p, js in zip(PERIODS, run_js(cases)):
        py = ref.compare(series, p, spy)
        assert not js.get("errors"), js
        assert (js["basis"], js["startDate"], js["endDate"], js["nReturns"]) == (py["basis"], py["startDate"], py["endDate"], py["nReturns"]), (group, p)
        for a, b in zip(js["stats"], py["stats"]):
            for k in ("cumulative", "annualized", "volatility", "beta", "correlationToBenchmark"):
                close(a[k], b[k], f"{group} {p} {a['symbol']} {k}")
            for k in ("depth",):
                close(a["maxDrawdown"][k], b["maxDrawdown"][k], f"{group} {p} {a['symbol']} dd")
            assert all(a["maxDrawdown"][k] == b["maxDrawdown"][k] for k in ("peakDate", "troughDate", "recoveryDate"))
        if py["correlation"] is None:
            assert js["correlation"] is None
        else:
            for ra, rb in zip(js["correlation"], py["correlation"]):
                for x, y in zip(ra, rb):
                    close(x, y, f"{group} {p} corr")


def test_one_basis_for_everyone_and_short_history_limits_the_window():
    spy = load("SPY")[0]
    js = run_js([{"list": load(*GROUPS["has_unknown_dividends"]), "period": "1Y", "benchmark": spy}, {"list": load(*GROUPS["short_history"]), "period": "MAX", "benchmark": spy},
                 {"list": load(*GROUPS["known_dividends"]), "period": "1Y", "benchmark": spy}])
    assert js[0]["basis"] == "price" and "PRICE_BASIS" in js[0]["warnings"]
    assert js[1]["startDate"] == "2024-03-21"                                       # RDDT's first day: all measured over the same dates
    assert js[2]["basis"] == "total"


def test_identical_series_correlate_perfectly_and_errors_are_reported():
    s = load("AAPL")[0]
    twin = dict(s, symbol="AAPL2")
    js = run_js([{"list": [s, twin], "period": "1Y", "benchmark": None}, {"list": [s], "period": "1Y"}, {"list": [s, dict(twin, dates=["2000-01-03", "2000-01-04"], close=[1, 2], volume=None, dividends=[])], "period": "MAX"}])
    assert abs(js[0]["correlation"][0][1] - 1) < 1e-12 and js[0]["stats"][0]["beta"] is None
    assert js[1]["errors"][0]["code"] == "TOO_FEW" and js[2]["errors"][0]["code"] == "NO_OVERLAP"
