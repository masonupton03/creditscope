"""Portfolio analytics: the JavaScript engine (assets/js/portfolio.js) against the independent Python reference
(tests/ref_portfolio.py) on realistic scenarios built from the simulated sample series, plus hand-checkable cases."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ref_portfolio as ref  # noqa: E402

SAMPLE = ROOT / "explorer" / "sample" / "series"
NODE = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")


def load(*syms):
    return {s: json.loads((SAMPLE / f"{s}.json").read_text()) for s in syms}


def tx(date, type, **kw):
    return dict(date=date, type=type, **kw)


def scenario_basic():
    s = load("SPY", "AAPL", "VTI", "TLT")
    return {"transactions": [
        tx("2023-01-03", "deposit", amount=20000),
        tx("2023-01-04", "buy", symbol="VTI", shares=40, price=s["VTI"]["close"][s["VTI"]["dates"].index("2023-01-04")], fee=1.5),
        tx("2023-01-04", "buy", symbol="AAPL", shares=25, price=140.0),
        tx("2023-06-15", "deposit", amount=5000),
        tx("2023-06-16", "buy", symbol="TLT", shares=30, price=95.0),
        tx("2024-02-02", "sell", symbol="AAPL", shares=10, price=185.0, fee=1),
        tx("2024-03-01", "withdrawal", amount=2500),
        tx("2024-05-10", "fee", amount=12.5),
        tx("2024-07-01", "buy", symbol="VTI", shares=5, price=270.0),
    ]}, s


def scenario_external_positions():
    s = load("SPY", "MSFT", "KO", "NVDA")                     # KO has unknown dividend history -> price basis
    return {"transactions": [
        tx("2022-03-01", "buy", symbol="MSFT", shares=12.5, price=290.0, external=True),
        tx("2022-03-01", "buy", symbol="KO", shares=100, price=60.0, external=True),
        tx("2023-09-05", "buy", symbol="NVDA", shares=8, price=450.0, external=True, fee=2),
        tx("2025-01-10", "sell", symbol="KO", shares=40, price=62.5, external=True),
    ]}, s


def scenario_split_manual_dividends_and_calendar():
    s = load("SPY", "JPM", "XOM")
    s["JPM"]["splits"] = [["2024-04-02", 2.0]]                 # a 2-for-1 split, applied to the share count
    return {"transactions": [
        tx("2023-02-01", "deposit", amount=30000),
        tx("2023-02-04", "buy", symbol="JPM", shares=50, price=300.0),          # a Saturday: applied on the next trading day
        tx("2023-02-06", "buy", symbol="XOM", shares=70, price=110.0),
        tx("2023-11-20", "dividend", symbol="XOM", amount=61.6),                # manual dividends replace XOM's automatic ones
        tx("2024-04-05", "sell", symbol="JPM", shares=40, price=150.0),         # post-split shares
        tx("2026-12-31", "deposit", amount=1000),                               # after the last price date: ignored
    ]}, s


def scenario_gap_before_listing():
    s = load("SPY", "RDDT")                                    # RDDT has no prices before 2024-03-21
    return {"transactions": [
        tx("2023-06-01", "deposit", amount=10000),
        tx("2024-01-10", "buy", symbol="RDDT", shares=20, price=40.0),
    ]}, s


def scenario_total_basis_all_known():
    s = load("SPY", "XOM", "V")
    return {"transactions": [
        tx("2021-12-01", "deposit", amount=10000),
        tx("2021-12-02", "buy", symbol="XOM", shares=50, price=60.0),
        tx("2022-12-01", "deposit", amount=4000),
        tx("2022-12-02", "buy", symbol="V", shares=15, price=210.0),
        tx("2025-06-02", "withdrawal", amount=3000),
    ]}, s


SCENARIOS = {f.__name__[9:]: f for f in (scenario_basic, scenario_external_positions, scenario_split_manual_dividends_and_calendar,
                                          scenario_gap_before_listing, scenario_total_basis_all_known)}


def run_js(cases):
    inp = ROOT / "tests" / "_pf_cases.json"
    try:
        inp.write_text(json.dumps({"cases": cases}))
        out = subprocess.run([NODE, str(ROOT / "tests/js/crosscheck_portfolio.js"), str(inp)], capture_output=True, text=True, check=True)
    finally:
        inp.unlink(missing_ok=True)
    return json.loads(out.stdout)


def close(a, b, msg, tol=1e-9):
    if a is None or b is None:
        assert a == b, msg
        return
    assert abs(a - b) <= tol * max(1.0, abs(a), abs(b)), f"{msg}: {a} vs {b}"


def compare_perf(js, py, tag):
    keys = ["days", "nReturns", "valueStart", "valueEnd", "valueChange", "netFlows", "investmentGain", "twr", "annualizedTwr",
            "modifiedDietz", "benchmarkReturn", "excess", "volatility", "benchmarkVolatility", "beta", "correlation"]
    assert js["startDate"] == py["startDate"] and js["endDate"] == py["endDate"] and js["truncated"] == py["truncated"], tag
    for k in keys:
        close(js[k], py[k], f"{tag} {k}")
    for k in ("depth", "peakDate", "troughDate", "recoveryDate"):
        if k == "depth":
            close(js["maxDrawdown"][k], py["maxDrawdown"][k], f"{tag} drawdown depth")
        else:
            assert js["maxDrawdown"][k] == py["maxDrawdown"][k], f"{tag} drawdown {k}"


@pytest.fixture(scope="module")
def results():
    names = list(SCENARIOS)
    cases = []
    for n in names:
        pf, s = SCENARIOS[n]()
        cases.append({"portfolio": pf, "series": s})
    js = run_js(cases)
    py = {n: ref.analyze(c["portfolio"], c["series"]) for n, c in zip(names, cases)}
    return dict(zip(names, js)), py


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_js_matches_independent_reference(results, name):
    js, py = results[0][name], results[1][name]
    assert not js.get("errors"), js
    assert js["basis"] == py["basis"] and js["startDate"] == py["startDate"] and js["mode"] == py["mode"]
    assert [(e["input"], e["date"], e["effectiveDate"], e["status"]) for e in sorted(js["ledger"], key=lambda e: e["input"])] == sorted(py["ledger"])
    for period, p in py["perf"].items():
        compare_perf(js["perf"][period], p, f"{name} {period}")
    for k, v in py["totals"].items():
        close(js["totals"][k], v, f"{name} totals.{k}")
    for k, v in py["concentration"].items():
        close(js["concentration"][k], v, f"{name} concentration.{k}")
    held = {h["symbol"]: h for h in js["holdings"]}
    assert set(held) == set(py["holdings"])
    for sym, r in py["holdings"].items():
        for k, v in r.items():
            close(held[sym][k], v, f"{name} {sym}.{k}")
    for a, b in zip(js["daily"]["value"], py["valueSeries"]):
        close(a, b, f"{name} daily value")
    assert len(js["daily"]["value"]) == len(py["valueSeries"])


def test_scenarios_exercise_the_features_they_claim(results):
    js = results[0]
    codes = lambda n: {w["code"] for w in js[n]["warnings"]}
    assert js["basic"]["basis"] == "total" and "PRICE_BASIS" not in codes("basic")
    assert js["external_positions"]["basis"] == "price"                                    # KO unknown dividends
    assert js["total_basis_all_known"]["basis"] == "total" and "PRICE_BASIS" not in codes("total_basis_all_known")
    assert "PRICE_GAP_EARLY" in codes("gap_before_listing")
    assert js["gap_before_listing"]["startDate"] == "2024-03-21"
    assert "TX_AFTER_END" in codes("split_manual_dividends_and_calendar")
    assert js["total_basis_all_known"]["perf"]["ITD"]["annualizedTwr"] is not None
    assert js["basic"]["perf"]["1M"]["annualizedTwr"] is None


def test_oversell_and_invalid_ledgers_are_rejected_not_computed():
    s = load("SPY", "VTI")
    over = {"transactions": [tx("2023-01-03", "deposit", amount=5000), tx("2023-01-04", "buy", symbol="VTI", shares=5, price=200.0),
                             tx("2023-02-01", "sell", symbol="VTI", shares=6, price=210.0)]}
    bad = {"transactions": [tx("2023-02-30", "deposit", amount=1), tx("2023-01-04", "buy", symbol="vti", shares=-1, price=0),
                            tx("2023-01-04", "gift", amount=5)]}
    missing = {"transactions": [tx("2023-01-04", "buy", symbol="ZZZZ", shares=1, price=1.0, external=True)]}
    out = run_js([{"portfolio": over, "series": s}, {"portfolio": bad, "series": s}, {"portfolio": missing, "series": s}])
    assert out[0]["errors"][0]["code"] == "OVERSELL"
    assert {e["code"] for e in out[1]["errors"]} >= {"BAD_DATE", "BAD_SYMBOL", "BAD_SHARES", "BAD_PRICE", "BAD_TYPE"}
    assert out[2]["errors"][0]["code"] == "NO_PRICES"
    with pytest.raises(ref.Oversell):
        ref.analyze(over, s)


@pytest.mark.parametrize("name", ["basic", "total_basis_all_known"])
@pytest.mark.parametrize("mode", ["cash", "reinvested", "price"])
def test_every_benchmark_methodology_matches_the_reference(name, mode):
    pf, s = SCENARIOS[name]()
    js = run_js([{"portfolio": pf, "series": s, "mode": mode}])[0]
    py = ref.analyze(pf, s, mode=mode)
    assert js["mode"] == py["mode"] == mode
    for period, p in py["perf"].items():
        compare_perf(js["perf"][period], p, f"{name} {mode} {period}")


def test_modes_give_different_benchmark_numbers_and_auto_follows_recorded_reinvestment():
    pf, s = SCENARIOS["total_basis_all_known"]()
    cash, reinv, price = (run_js([{"portfolio": pf, "series": s, "mode": m}])[0]["perf"]["ITD"]["benchmarkReturn"] for m in ("cash", "reinvested", "price"))
    assert price < cash < reinv                      # dividends add, and reinvesting them adds more than leaving them idle
    auto = run_js([{"portfolio": pf, "series": s}])[0]
    assert auto["mode"] == "cash" and "not reinvested" in auto["basisLabel"]
    pf2 = json.loads(json.dumps(pf))
    pf2["transactions"].append(tx("2022-06-01", "buy", symbol="XOM", shares=1, price=70.0, reinvest=True))
    auto2 = run_js([{"portfolio": pf2, "series": s}])[0]
    assert auto2["mode"] == "reinvested" and "reinvested on the ex-date" in auto2["basisLabel"]
