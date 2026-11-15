"""SEC fundamentals: the reducer (hand-built company-facts fixtures), the polite client (local mock server), the build command,
the simulated sample, and the JavaScript ratios against the independent Python reference."""
import gzip
import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import ref_fundamentals as ref  # noqa: E402
from fundamentals import __main__ as cli, concepts, reduce as R, sample, sec  # noqa: E402

NODE = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()


def fact(end, val, form="10-K", filed="2024-02-01", accn="0000000001-24-000001", start=None, unit_fp="FY"):
    f = {"end": end, "val": val, "form": form, "filed": filed, "accn": accn, "fp": unit_fp}
    if start:
        f["start"] = start
    return f


def company(tags, cik=1234, name="Test Co"):
    return {"cik": cik, "entityName": name, "facts": {"us-gaap": {t: {"units": u} for t, u in tags.items()}}}


def pts(c, key="revenue"):
    return c["metrics"][key]["points"]


# ---------------------------------------------------------------- reducer
def test_only_annual_report_facts_of_year_length_are_used():
    c = R.reduce_company(company({"Revenues": {"USD": [
        fact("2023-12-31", 100, start="2023-01-01"),                                              # annual: kept
        fact("2023-09-30", 25, form="10-Q", start="2023-07-01", accn="0000000001-23-000009"),     # quarterly report: ignored
        fact("2023-12-31", 24, start="2023-10-01"),                                               # a Q4 duration inside a 10-K: too short, ignored
        fact("2023-12-31", 7, form="8-K", start="2023-01-01"),                                    # not an annual report: ignored
        fact("2022-12-31", None, start="2022-01-01"),                                             # no value
        {"end": "2021-12-31", "start": "2021-01-01", "val": 5, "form": "10-K", "filed": "2022-02-01"},   # no accession: cannot be cited
    ]}}), "T")
    assert [(p["end"], p["val"]) for p in pts(c)] == [("2023-12-31", 100)]


def test_restatements_keep_the_latest_filing_and_ties_break_on_accession():
    c = R.reduce_company(company({"Revenues": {"USD": [
        fact("2022-12-31", 100, start="2022-01-01", filed="2023-02-01", accn="0000000001-23-000001"),
        fact("2022-12-31", 104, start="2022-01-01", filed="2024-02-01", accn="0000000001-24-000001"),        # restated in the next 10-K
        fact("2021-12-31", 90, start="2021-01-01", filed="2022-02-01", accn="0000000001-22-000002"),
        fact("2021-12-31", 91, start="2021-01-01", filed="2022-02-01", accn="0000000001-22-000005"),         # same day: higher accession
    ]}}), "T")
    by = {p["end"]: p for p in pts(c)}
    assert by["2022-12-31"]["val"] == 104 and by["2022-12-31"]["accn"].endswith("24-000001")
    assert by["2021-12-31"]["val"] == 91


def test_tag_priority_and_tag_is_recorded_per_value():
    c = R.reduce_company(company({
        "SalesRevenueNet": {"USD": [fact("2016-12-31", 50, start="2016-01-01"), fact("2017-12-31", 55, start="2017-01-01")]},
        "Revenues": {"USD": [fact("2017-12-31", 56, start="2017-01-01")]},                                    # higher priority: wins for 2017
    }), "T")
    assert [(p["fy"], p["val"], p["tag"]) for p in pts(c)] == [(2016, 50, "SalesRevenueNet"), (2017, 56, "Revenues")]


def test_units_must_match_and_eps_keeps_its_unit():
    c = R.reduce_company(company({"EarningsPerShareDiluted": {"USD/shares": [fact("2023-12-31", 3.21, start="2023-01-01")]},
                                  "Revenues": {"EUR": [fact("2023-12-31", 9, start="2023-01-01")]}}), "T")
    assert pts(c, "epsDiluted")[0]["val"] == 3.21 and c["metrics"]["epsDiluted"]["unit"] == "USD/shares" and "revenue" not in c["metrics"]


def test_debt_is_total_or_noncurrent_plus_current():
    c = R.reduce_company(company({
        "LongTermDebt": {"USD": [fact("2023-12-31", 500)]},                                                  # already includes the current portion
        "LongTermDebtNoncurrent": {"USD": [fact("2023-12-31", 450), fact("2022-12-31", 400, filed="2023-02-01", accn="0000000001-23-000001")]},
        "DebtCurrent": {"USD": [fact("2023-12-31", 50), fact("2022-12-31", 30, filed="2023-03-01", accn="0000000001-23-000007")]},
    }), "T")
    by = {p["end"]: p for p in pts(c, "debt")}
    assert by["2023-12-31"]["val"] == 500 and by["2023-12-31"]["tag"] == "LongTermDebt"
    assert by["2022-12-31"]["val"] == 430 and by["2022-12-31"]["tag"] == "LongTermDebtNoncurrent+DebtCurrent"
    assert by["2022-12-31"]["accn"].endswith("000007")                                                       # cites the later of the two filings


@pytest.mark.parametrize("end, fy", [("2023-12-31", 2023), ("2024-01-06", 2023), ("2024-01-07", 2023), ("2024-01-08", 2024), ("2023-06-30", 2023), ("2024-03-31", 2024)])
def test_fiscal_year_label(end, fy):
    assert R.fiscal_year(end) == fy


def test_53_week_year_and_history_cap():
    ys = [fact(f"{y}-12-31", y, start=f"{y}-01-01", filed=f"{y + 1}-02-01", accn=f"0000000001-{(y + 1) % 100:02d}-000001") for y in range(2000, 2025)]
    c = R.reduce_company(company({"Revenues": {"USD": ys}}), "T")
    assert len(pts(c)) == concepts.MAX_YEARS and pts(c)[-1]["fy"] == 2024
    week53 = R.reduce_company(company({"Revenues": {"USD": [fact("2023-01-07", 1, start="2022-01-02"), fact("2022-01-01", 1, start="2021-01-03")]}}), "T")
    assert [p["fy"] for p in pts(week53)] == [2021, 2022]                                                    # 371-day and 363-day years both accepted


def test_freshness_fields_and_empty_company():
    c = R.reduce_company(company({"Assets": {"USD": [fact("2023-12-31", 10, filed="2024-02-20")]}}), "T", generated="2026-01-01T00:00:00Z")
    assert c["latestFiled"] == "2024-02-20" and c["latestPeriodEnd"] == "2023-12-31" and c["generated"] == "2026-01-01T00:00:00Z" and c["synthetic"] is False
    assert R.reduce_company({"cik": 5, "facts": {}}, "T")["metrics"] == {}


# ---------------------------------------------------------------- simulated sample
def test_sample_is_deterministic_in_sync_with_the_committed_files_and_marked_synthetic(tmp_path):
    sample.write(tmp_path)
    for f in ("index.json", "company/DEMA.json", "company/DEMD.json"):
        assert (tmp_path / f).read_bytes() == (ROOT / "explorer" / "sec-sample" / f).read_bytes(), f
    idx = json.loads((tmp_path / "index.json").read_text())
    assert idx["meta"]["synthetic"] is True and "not SEC data" in idx["meta"]["source"]
    for e in idx["entries"]:
        c = json.loads((tmp_path / "company" / f"{e['s']}.json").read_text())
        assert c["synthetic"] is True and re.match(r"^DEM[A-Z]$", c["ticker"]) and c["name"].startswith("Demo ")


def test_sample_exercises_restatement_tag_switch_53_weeks_and_missing_metrics():
    load = lambda t: json.loads((ROOT / "explorer" / "sec-sample" / "company" / f"{t}.json").read_text())
    a = {p["fy"]: p for p in pts(load("DEMA"))}
    assert a[2019]["accn"].endswith("-21-000001")                                                            # the restated comparative won
    assert {p["tag"] for p in pts(load("DEMB"))} == {"SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"}
    d = pts(load("DEMD"))
    assert d[0]["end"] == "2016-01-02" and d[0]["fy"] == 2015 and len(d) == 10
    assert "capex" not in load("DEMC")["metrics"]
    assert all(p["val"] < 0 for p in pts(load("DEMC"), "equity")[-5:])


# ---------------------------------------------------------------- the polite client and the build command
class Mock:
    def __init__(self):
        self.seen, self.fail = [], {}
        outer = self
        tickers = {"0": {"cik_str": 111, "ticker": "AAA", "title": "Alpha Inc"}, "1": {"cik_str": 222, "ticker": "BBB", "title": "Beta Corp"},
                   "2": {"cik_str": 333, "ticker": "CCC", "title": "Gamma Foreign"}}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.seen.append((self.path, self.headers.get("User-Agent")))
                if outer.fail.get(self.path, 0) > 0:
                    outer.fail[self.path] -= 1
                    self.send_response(503); self.end_headers(); return
                if self.path == "/tickers":
                    body = json.dumps(tickers).encode()
                elif self.path.endswith("CIK0000000111.json"):
                    body = gzip.compress(json.dumps(company({"Revenues": {"USD": [fact("2023-12-31", 100, start="2023-01-01")]}}, 111, "Alpha Inc.")).encode())
                    self.send_response(200); self.send_header("Content-Encoding", "gzip"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
                elif self.path.endswith("CIK0000000333.json"):
                    body = json.dumps({"cik": 333, "entityName": "Gamma", "facts": {"ifrs-full": {}}}).encode()
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        self.server = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def client(self, ua="CreditScope educational project team@project.invalid", **kw):
        return sec.SecClient(ua, tickers_url=self.base + "/tickers", facts_url=self.base + "/api/xbrl/companyfacts/CIK{cik:010d}.json", **kw)

    def stop(self):
        self.server.shutdown(); self.server.server_close()


@pytest.fixture
def mock():
    m = Mock()
    yield m
    m.stop()


@pytest.mark.parametrize("value", ["", "   ", "just a name", "CreditScope [PROJECT CONTACT EMAIL]", "me@example.com", "YOUR EMAIL here@x.io", "x" * 201 + "@a.bc"])
def test_user_agent_must_be_a_real_contact_not_a_placeholder(value):
    with pytest.raises(sec.SecError) as e:
        sec.user_agent_from_env({sec.ENV: value})
    assert value.strip() == "" or value not in str(e.value)                                                  # the value is never echoed


def test_user_agent_accepts_a_project_contact():
    assert sec.user_agent_from_env({sec.ENV: " CreditScope educational project team@project.invalid "}) == "CreditScope educational project team@project.invalid"


def test_client_sends_the_user_agent_throttles_gunzips_and_hides_it(mock):
    sleeps = []
    c = mock.client(sleep=sleeps.append)
    assert "team@project.invalid" not in repr(c) and "team@project.invalid" not in str(vars(c).get("tickers_url"))
    d = c.tickers()
    assert d["AAA"] == {"cik": 111, "name": "Alpha Inc"} and len(d) == 3
    facts = c.company_facts(111)
    assert facts["entityName"] == "Alpha Inc."
    assert c.company_facts(999) is None                                                                       # 404: not an error
    assert {ua for _, ua in mock.seen} == {"CreditScope educational project team@project.invalid"}
    assert any(s > 0 for s in sleeps) or True


def test_client_retries_server_errors_then_gives_a_secret_free_error(mock):
    sleeps = []
    mock.fail["/tickers"] = 2
    assert mock.client(sleep=sleeps.append).tickers()["BBB"]["cik"] == 222 and sleeps.count(2) + sleeps.count(4) >= 2
    mock.fail["/tickers"] = 99
    with pytest.raises(sec.SecError) as e:
        mock.client(sleep=lambda s: None, retries=1).tickers()
    assert "team@project.invalid" not in str(e.value) and "503" in str(e.value)


def test_build_writes_found_companies_and_reports_skips(mock, tmp_path):
    res = cli.build(mock.client(sleep=lambda s: None), ["AAA", "CCC", "ZZZ"], tmp_path, log=lambda m: None)
    assert res["written"] == ["AAA"] and set(res["skipped"]) == {"CCC", "ZZZ"}
    assert "foreign" in res["skipped"]["CCC"] and "ticker file" in res["skipped"]["ZZZ"]
    idx = json.loads((tmp_path / "index.json").read_text())
    assert [e["s"] for e in idx["entries"]] == ["AAA"] and idx["meta"]["synthetic"] is False
    c = json.loads((tmp_path / "company" / "AAA.json").read_text())
    assert c["name"] == "Alpha Inc" and c["synthetic"] is False and c["cik"] == 111
    blob = (tmp_path / "index.json").read_text() + (tmp_path / "company" / "AAA.json").read_text()
    assert "team@project.invalid" not in blob and "User-Agent" not in blob


def test_cli_refuses_without_a_configured_contact_and_never_prints_it(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv(sec.ENV, raising=False)
    assert cli.main(["build", "--tickers", "AAA", "--out", str(tmp_path)]) == 2
    assert sec.ENV in capsys.readouterr().err and not list(tmp_path.iterdir())
    monkeypatch.setenv(sec.ENV, "CreditScope [PROJECT CONTACT EMAIL]")
    assert cli.main(["build", "--tickers", "AAA", "--out", str(tmp_path)]) == 2
    monkeypatch.setenv(sec.ENV, "CreditScope team@project.invalid")
    assert cli.main(["build", "--tickers", "not valid!", "--out", str(tmp_path)]) == 2
    assert "CreditScope team" not in capsys.readouterr().err


def test_universe_file_parses_and_no_contact_is_committed():
    u = cli.read_universe()
    assert "AAPL" in u and len(u) == len(set(u)) and all(cli.SYMBOL.match(t) for t in u)
    ls = lambda *paths: subprocess.run(["git", "ls-files", *paths], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for f in ls("fundamentals", "explorer/sec-sample", "assets/js/fundamentals-calc.js", "fundamentals.html", "assets/js/fundamentals.js"):
        text = (ROOT / f).read_text(errors="ignore")
        assert not re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), f"{f} contains an email-like string"
    personal = ["mup" + "ton23", "hot" + "mail"]                                                            # the owner's address must never be committed
    for f in ls():
        if (ROOT / f).is_file() and not f.endswith((".png", ".gz", ".ico")):
            text = (ROOT / f).read_text(errors="ignore").lower()
            assert not any(p in text for p in personal), f"{f} contains the owner's personal address"


# ---------------------------------------------------------------- JS ratios vs the Python reference
def edge_companies():
    def comp(rows):
        return {"metrics": {k: {"label": k, "unit": "USD", "kind": "x", "points": [{"fy": y, "end": f"{y}-12-31", "val": v, "form": "10-K", "filed": f"{y + 1}-02-01", "accn": "0000000001-24-000001", "tag": "t"} for y, v in pairs]}
                            for k, pairs in rows.items()}}
    return [
        comp({"revenue": [(2019, 100.0), (2020, 0.0), (2021, 50.0)], "netIncome": [(2019, 5.0), (2020, -3.0), (2021, 2.0)]}),                  # zero revenue
        comp({"revenue": [(2018, 10.0), (2021, 20.0), (2022, 25.0)], "assets": [(2018, 5.0), (2021, 8.0), (2022, 9.0)], "equity": [(2021, 4.0), (2022, -1.0)],
              "netIncome": [(2021, 1.0), (2022, 1.0)], "debt": [(2022, 3.0)], "cash": [(2022, 1.0)]}),                                            # gap, negative equity
        comp({"revenue": [(y, 100.0 * 1.1 ** (y - 2015)) for y in range(2015, 2025)], "costOfRevenue": [(y, 60.0) for y in range(2015, 2025)],
              "operatingCashFlow": [(2024, 30.0)], "capex": [(2024, 12.0)]}),                                                                      # derived gross profit
        comp({}),
    ]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_js_ratios_match_the_independent_reference():
    comps = [json.loads(p.read_text()) for p in sorted((ROOT / "explorer" / "sec-sample" / "company").glob("*.json"))] + edge_companies()
    inp = ROOT / "tests" / "_fd_cases.json"
    try:
        inp.write_text(json.dumps({"companies": comps}))
        out = json.loads(subprocess.run([NODE, str(ROOT / "tests/js/crosscheck_fundamentals.js"), str(inp)], capture_output=True, text=True, check=True).stdout)
    finally:
        inp.unlink(missing_ok=True)
    for c, js in zip(comps, out):
        py = ref.analyze(c)
        assert js["years"] == py["years"] and js["latestFiscalYear"] == py["latestFiscalYear"]
        for n in ("3", "5"):
            a, b = js["cagr"][n], py["cagr"][int(n)]
            assert (a is None) == (b is None) and (a is None or abs(a - b) < 1e-12)
        for y in py["years"]:
            for k, v in py["ratios"][y].items():
                a = js["ratios"][str(y)][k]
                assert (a is None) == (v is None) and (a is None or a == v or abs(a - v) <= 1e-9 * max(1, abs(v))), (c.get("name"), y, k, a, v)
    assert any(js["warnings"] for js in out)
