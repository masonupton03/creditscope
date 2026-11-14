"""Stock Explorer: the Python reference calculations, the simulated sample data, and the check that the
browser module (assets/js/finance.js) agrees with the independent Python implementation."""
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import make_explorer_fixtures  # noqa: E402
import make_explorer_sample  # noqa: E402
import ref_finance as ref  # noqa: E402
from conftest import approx_equal  # noqa: E402

SAMPLE = ROOT / "explorer" / "sample"
NODE = shutil.which("node")


def weekdays(n, start=date(2026, 1, 5)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def series(close, **kw):
    s = {"dates": weekdays(len(close)), "close": close, "volume": None, "dividends": None}
    s.update(kw)
    return s


def from_returns(rets, p0=100.0):
    out = [p0]
    for r in rets:
        out.append(out[-1] * (1 + r))
    return out


# ---------- the reference implementation against hand-computed answers ----------

def test_period_start_dates():
    assert ref.start_date("1M", "2026-11-13", "x") == "2026-10-13"
    assert ref.start_date("1Y", "2026-11-13", "x") == "2025-11-13"
    assert ref.start_date("YTD", "2026-11-13", "x") == "2025-12-31"
    assert ref.start_date("1M", "2026-03-31", "x") == "2026-02-28"
    assert ref.start_date("1M", "2024-03-31", "x") == "2024-02-29"
    assert ref.start_date("1Y", "2024-02-29", "x") == "2023-02-28"
    assert ref.start_date("MAX", "2026-11-13", "2016-11-14") == "2016-11-14"


def test_price_return_and_label_when_dividends_unknown():
    r = ref.summarize(series([100, 110, 121]), "MAX")
    assert r["basis"] == "price" and r["totalReturn"] is None
    assert r["cumulativeReturn"] == pytest.approx(0.21) and r["priceReturn"] == pytest.approx(0.21)


def test_total_return_reinvests_dividends_price_return_does_not():
    d = weekdays(3)
    r = ref.summarize({"dates": d, "close": [100, 100, 100], "volume": None, "dividends": [[d[2], 2]]}, "MAX")
    assert r["basis"] == "total"
    assert r["totalReturn"] == pytest.approx(0.02) and r["priceReturn"] == pytest.approx(0.0)
    assert r["cumulativeReturn"] == pytest.approx(0.02)


def test_known_no_dividends_equals_price_return():
    r = ref.summarize(series([100, 105, 95, 120], dividends=[]), "MAX")
    assert r["basis"] == "total" and r["totalReturn"] == pytest.approx(r["priceReturn"])


def test_weekend_ex_date_credited_to_next_trading_day():
    s = {"dates": ["2026-01-02", "2026-01-05", "2026-01-06"], "close": [100, 100, 100], "volume": None,
         "dividends": [["2026-01-03", 1], ["2025-12-01", 5], ["2026-02-01", 7], ["2026-01-02", 9]]}
    assert ref.credited_dividends(s) == {1: 1}
    assert ref.level_series(s, "total")[2] == pytest.approx(1.01)


def test_compounding_chain():
    d = weekdays(3)
    s = {"dates": d, "close": [100, 102, 101], "volume": None, "dividends": [[d[1], 1], [d[2], 1]]}
    lv = ref.level_series(s, "total")
    assert lv[1] == pytest.approx(1.03) and lv[2] == pytest.approx(1.03 * 102 / 102)


def test_drawdown_cases():
    d = weekdays(4)
    dd = ref.drawdown([100, 90, 99, 110], [0, 1, 2, 3], d)
    assert dd["depth"] == pytest.approx(-0.1) and (dd["peakDate"], dd["troughDate"], dd["recoveryDate"]) == (d[0], d[1], d[3])
    assert ref.drawdown([100, 80, 90, 95], [0, 1, 2, 3], d)["recoveryDate"] is None
    assert ref.drawdown([100, 120, 60, 90], [0, 1, 2, 3], d)["depth"] == pytest.approx(-0.5)
    assert ref.drawdown([1, 2, 3, 4], [0, 1, 2, 3], d) == {"depth": 0.0, "peakDate": None, "troughDate": None, "recoveryDate": None}


def test_drawdown_ignores_floating_point_noise():
    d = weekdays(5)
    dd = ref.drawdown([1, 1.5, 1.5 * (1 + 1e-15), 1.2, 1.5 * (1 - 1e-15)], [0, 1, 2, 3, 4], d)
    assert (dd["peakDate"], dd["troughDate"], dd["recoveryDate"]) == (d[1], d[3], d[4])


def test_annualised_return_needs_a_year():
    r = ref.summarize({"dates": ["2025-01-01", "2026-02-05"], "close": [100, 200], "volume": None, "dividends": None}, "MAX")
    assert r["days"] == 400 and r["annualizedReturn"] == pytest.approx(2 ** (365.25 / 400) - 1)
    assert ref.summarize({"dates": ["2025-01-01", "2025-12-31"], "close": [100, 200], "volume": None, "dividends": None}, "MAX")["annualizedReturn"] is None


def test_volatility_annualisation_and_minimum():
    rets = [0.01 if i % 2 == 0 else -0.01 for i in range(40)]
    r = ref.summarize(series(from_returns(rets)), "MAX")
    assert r["volatility"] == pytest.approx(math.sqrt(40 * 0.0001 / 39) * math.sqrt(252))
    assert ref.summarize(series(from_returns(rets[:10])), "MAX")["volatility"] is None


def test_beta_and_correlation():
    n = 130
    rb = [((i * 37) % 11 - 5) / 400 for i in range(n - 1)]
    a = series(from_returns([2 * x for x in rb]), dividends=[])
    b = series(from_returns(rb), dividends=[])
    c = ref.compare(a, b, "MAX")
    assert c["basis"] == "total" and c["beta"] == pytest.approx(2) and c["correlation"] == pytest.approx(1)
    assert ref.compare(series(from_returns([2 * x for x in rb[:40]]), dividends=[]), series(from_returns(rb[:40]), dividends=[]), "MAX")["beta"] is None
    assert ref.compare(series(a["close"], dividends=None), b, "MAX")["basis"] == "price"


# ---------- properties that must hold for any series ----------

def random_series(rng, n, with_div=True, missing_volume=True):
    dates = weekdays(n, date(2020, 1, 6) + timedelta(days=rng.randint(0, 400)))
    r = [rng.gauss(0.0003, 0.012) if rng.random() > 0.15 else 0.0 for _ in range(n - 1)]     # some flat days
    close = [round(x, 2) for x in from_returns(r, rng.uniform(20, 300))]
    close = [max(c, 0.5) for c in close]
    divs = None
    if with_div:
        divs = []
        for k in range(rng.randint(0, 8)):
            d0 = date.fromisoformat(dates[0]) + timedelta(days=rng.randint(-20, (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 20))
            divs.append([d0.isoformat(), round(rng.uniform(0.05, 1.5), 4)])               # may fall on weekends or outside the range
        divs.sort()
    vol = [int(rng.uniform(1e5, 1e7)) if not (missing_volume and rng.random() < 0.05) else None for _ in range(n)]
    return {"dates": dates, "close": close, "volume": vol, "dividends": divs}


@pytest.mark.parametrize("seed", range(25))
def test_properties_hold_for_random_series(seed):
    rng = random.Random(seed)
    s = random_series(rng, rng.randint(30, 900))
    for period in ref.PERIODS:
        r = ref.summarize(s, period)
        if "cumulativeReturn" not in r:
            continue
        assert -1.0 <= r["maxDrawdown"]["depth"] <= 0.0
        assert r["cumulativeReturn"] > -1.0
        if s["dividends"] is not None:
            assert r["totalReturn"] == pytest.approx(r["cumulativeReturn"])
            assert r["totalReturn"] >= r["priceReturn"] - 1e-12               # reinvested dividends can only add (all are positive)
        else:
            assert r["totalReturn"] is None
        i0, i1, _ = ref.window(s, period)
        levels = ref.level_series(s, r["basis"])
        rets = ref.simple_returns(levels, list(range(i0, i1 + 1)))
        assert math.prod(1 + x for x in rets) - 1 == pytest.approx(r["cumulativeReturn"], rel=1e-9, abs=1e-12)
        if r["volatility"] is not None:
            assert r["volatility"] >= 0


@pytest.mark.parametrize("seed", range(10))
def test_no_dividends_means_total_equals_price(seed):
    rng = random.Random(1000 + seed)
    s = random_series(rng, 200, with_div=False)
    s["dividends"] = []
    assert ref.level_series(s, "total") == pytest.approx([c / s["close"][0] for c in s["close"]])


# ---------- the simulated sample data ----------

def test_sample_data_integrity():
    index = json.loads((SAMPLE / "index.json").read_text())
    assert index["meta"]["synthetic"] is True and "not real" in index["meta"]["provider"].lower()
    syms = [e["s"] for e in index["entries"]]
    assert len(syms) == len(set(syms)) == index["meta"]["count"] and "SPY" in syms
    files = sorted(p.stem for p in (SAMPLE / "series").glob("*.json"))
    assert files == sorted(syms)
    states = set()
    for sym in syms:
        s = json.loads((SAMPLE / "series" / (sym + ".json")).read_text())
        assert s["synthetic"] is True and s["symbol"] == sym
        d = s["dates"]
        assert d == sorted(d) and len(set(d)) == len(d)
        assert all(date.fromisoformat(x).weekday() < 5 for x in d)
        assert len(d) == len(s["close"]) == len(s["volume"])
        assert all(c > 0 for c in s["close"]) and all(v > 0 for v in s["volume"])
        if s["dividends"] is None:
            states.add("unknown")
        else:
            states.add("none" if not s["dividends"] else "paid")
            assert all(d[0] < x[0] <= d[-1] and x[1] > 0 for x in s["dividends"])
    assert states == {"unknown", "none", "paid"}                              # every labelling state is represented
    assert json.loads((SAMPLE / "series" / "RDDT.json").read_text())["dates"][0] == "2024-03-21"      # a short history


def test_sample_data_is_current():
    index, series_out = make_explorer_sample.simulate()
    assert json.loads((SAMPLE / "index.json").read_text()) == index
    for sym, s in series_out.items():
        stored = json.loads((SAMPLE / "series" / (sym + ".json")).read_text())
        assert stored["dates"] == s["dates"], sym
        approx_equal(stored["close"], s["close"], sym + ".close", rel=1e-6)
        approx_equal(stored["volume"], s["volume"], sym + ".volume", rel=1e-6)
        approx_equal(stored["dividends"], s["dividends"], sym + ".dividends", rel=1e-6)


def test_expected_results_are_current():
    approx_equal(make_explorer_fixtures.build_expected(), json.loads((ROOT / "tests/fixtures/explorer_expected.json").read_text()), "expected", rel=1e-9)


# ---------- browser module vs independent Python on awkward random data ----------

@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_browser_module_matches_python_on_random_series():
    cases, refs = [], []
    for seed in range(40):
        rng = random.Random(seed)
        s = random_series(rng, rng.randint(25, 700), with_div=seed % 4 != 0)
        b = random_series(random.Random(500 + seed), rng.randint(60, 700), with_div=seed % 3 != 0)
        for period in ref.PERIODS:
            bench = b if seed % 2 == 0 else None
            cases.append({"series": s, "bench": bench, "period": period})
            refs.append(ref.summarize(s, period, bench))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cases.json"
        path.write_text(json.dumps({"cases": cases}))
        proc = subprocess.run([NODE, "tests/js/crosscheck.js", str(path)], cwd=ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        got = json.loads(proc.stdout)
    assert len(got) == len(refs)
    for i, (g, r) in enumerate(zip(got, refs)):
        approx_equal(g, r, f"case{i}")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("name", ["finance", "search"])
def test_node_unit_tests(name):
    out = subprocess.run([NODE, "--test", f"tests/js/{name}.test.js"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
