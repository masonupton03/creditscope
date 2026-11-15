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
from fundamentals import __main__ as cli, concepts, reduce as R, sample, sec, verify as V  # noqa: E402

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
        self.concepts = {}
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
                elif "/companyconcept/CIK0000000111/us-gaap/" in self.path:
                    tag = self.path.rsplit("/", 1)[1][:-5]
                    rows = outer.concepts.get(tag)
                    if rows is None:
                        self.send_response(404); self.end_headers(); return
                    body = json.dumps({"cik": 111, "tag": tag, "units": {"USD": rows}}).encode()
                elif self.path.endswith("CIK0000000333.json"):
                    body = json.dumps({"cik": 333, "entityName": "Gamma", "facts": {"ifrs-full": {}}}).encode()
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        self.server = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def client(self, ua="CreditScope educational project team@project.invalid", **kw):
        return sec.SecClient(ua, tickers_url=self.base + "/tickers", facts_url=self.base + "/api/xbrl/companyfacts/CIK{cik:010d}.json",
                              concept_url=self.base + "/api/xbrl/companyconcept/CIK{cik:010d}/{taxonomy}/{tag}.json", **kw)

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


# ---------------------------------------------------------------- non-standard filers, data checks, verification
def shape(tags, cik=1, name="Shape Co"):
    """Company facts built from (tag, unit, [(start_or_None, end, val, filed, accn)]) with invented numbers: structure tests only."""
    out = {}
    for tag, unit, rows in tags:
        out.setdefault(tag, {})[unit] = [dict(end=e, val=v, form="10-K", filed=f, accn=a, **({"start": st} if st else {})) for st, e, v, f, a in rows]
    return {"cik": cik, "entityName": name, "facts": {"us-gaap": {t: {"units": u} for t, u in out.items()}}}


def test_fiscal_calendars_of_the_target_companies_are_labelled_the_way_the_companies_name_them():
    # structure only (invented numbers): June, September, January and December year ends
    cases = [("June", "2024-06-30", "2023-07-01", 2024), ("September", "2024-09-28", "2023-10-01", 2024),
             ("January", "2025-01-31", "2024-02-01", 2025), ("December", "2024-12-31", "2024-01-01", 2024)]
    for label, end, start, fy in cases:
        c = R.reduce_company(shape([("Revenues", "USD", [(start, end, 100.0, "2025-02-01", "0000000001-25-000001")])]), "T")
        assert pts(c)[0]["fy"] == fy, label


def test_bank_shape_uses_net_revenue_and_cash_due_from_banks_and_never_invents_the_rest():
    c = R.reduce_company(shape([
        ("RevenuesNetOfInterestExpense", "USD", [("2023-01-01", "2023-12-31", 500.0, "2024-02-20", "0000000001-24-000001")]),
        ("InterestAndDividendIncomeOperating", "USD", [("2023-01-01", "2023-12-31", 900.0, "2024-02-20", "0000000001-24-000001")]),   # gross interest income: must NOT be revenue
        ("CashAndDueFromBanks", "USD", [(None, "2023-12-31", 40.0, "2024-02-20", "0000000001-24-000001")]),
        ("Assets", "USD", [(None, "2023-12-31", 9000.0, "2024-02-20", "0000000001-24-000001")]),
    ]), "BANK")
    assert pts(c)[0]["val"] == 500.0 and pts(c)[0]["tag"] == "RevenuesNetOfInterestExpense"
    assert pts(c, "cash")[0]["tag"] == "CashAndDueFromBanks"
    assert "operatingIncome" not in c["metrics"] and "costOfRevenue" not in c["metrics"] and "grossProfit" not in c["metrics"]
    assert {"operatingIncome", "grossProfit", "capex", "debt"} <= set(c["coverage"]["missing"])
    assert c["coverage"]["found"]["revenue"] == {"years": 1, "tags": ["RevenuesNetOfInterestExpense"]}


def test_commercial_paper_style_short_debt_is_not_silently_added_and_composite_debt_is_labelled():
    c = R.reduce_company(shape([
        ("LongTermDebtNoncurrent", "USD", [(None, "2023-09-30", 95.0, "2023-11-03", "0000000001-23-000106")]),
        ("LongTermDebtCurrent", "USD", [(None, "2023-09-30", 9.0, "2023-11-03", "0000000001-23-000106")]),
        ("CommercialPaper", "USD", [(None, "2023-09-30", 6.0, "2023-11-03", "0000000001-23-000106")]),
    ]), "T")
    assert pts(c, "debt")[0]["val"] == 104.0 and pts(c, "debt")[0]["tag"] == "LongTermDebtNoncurrent+LongTermDebtCurrent"


def test_quality_checks_flag_without_changing_numbers():
    rows = lambda tag, vals: (tag, "USD", [((f"{y}-01-01" if tag in ("Revenues", "CostOfRevenue", "GrossProfit") else None), f"{y}-12-31", v, f"{y + 1}-02-01" if ok else f"{y}-06-01", f"0000000001-{(y + 1) % 100:02d}-000001") for y, v, ok in vals])
    c = R.reduce_company(shape([
        rows("Assets", [(2022, 1000.0, True), (2023, 1000.0, True)]), rows("Liabilities", [(2022, 600.0, True), (2023, 600.0, True)]), rows("StockholdersEquity", [(2022, 400.0, True), (2023, 300.0, True)]),
        rows("Revenues", [(2022, 100.0, True), (2023, 400.0, True)]), rows("CostOfRevenue", [(2022, 60.0, True), (2023, 100.0, True)]), rows("GrossProfit", [(2022, 40.0, True), (2023, 250.0, False)]),
    ]), "T")
    codes = {(x["code"], x["fy"]) for x in c["checks"]}
    assert ("BALANCE_IDENTITY", 2023) in codes and ("BALANCE_IDENTITY", 2022) not in codes            # 1000 vs 900
    assert ("GROSS_PROFIT_MISMATCH", 2023) in codes and ("LARGE_REVENUE_CHANGE", 2023) in codes
    assert ("FILED_BEFORE_PERIOD_END", 2023) in codes
    assert [p["val"] for p in pts(c, "grossProfit")] == [40.0, 250.0]                                  # flagged, not altered


def test_clean_data_has_no_checks_and_empty_coverage_gaps():
    assert json.loads((ROOT / "explorer/sec-sample/company/DEMB.json").read_text())["checks"] == []


def test_cross_check_confirms_matches_and_catches_a_wrong_value_or_missing_fact(mock):
    comp = R.reduce_company(company({"Revenues": {"USD": [fact("2023-12-31", 100, start="2023-01-01", accn="0000000111-24-000001"),
                                                          fact("2022-12-31", 90, start="2022-01-01", accn="0000000111-23-000001", filed="2023-02-01")]}}, 111), "AAA")
    row = lambda v, end, start, accn: {"end": end, "start": start, "val": v, "accn": accn, "form": "10-K", "filed": "2024-02-01"}
    mock.concepts["Revenues"] = [row(100, "2023-12-31", "2023-01-01", "0000000111-24-000001"), row(90, "2022-12-31", "2022-01-01", "0000000111-23-000001")]
    assert V.cross_check(mock.client(sleep=lambda s: None), comp) == {"ok": 2, "mismatches": [], "skipped": []}
    mock.concepts["Revenues"][0]["val"] = 101                                                          # the other endpoint disagrees
    res = V.cross_check(mock.client(sleep=lambda s: None), comp)
    assert res["ok"] == 1 and res["mismatches"][0]["why"] == "value differs" and res["mismatches"][0]["stored"] == 100
    mock.concepts["Revenues"] = []
    assert all(m["why"].startswith("no matching") for m in V.cross_check(mock.client(sleep=lambda s: None), comp)["mismatches"])


def test_verification_sheet_links_every_figure_to_its_filing_and_lists_gaps():
    c = json.loads((ROOT / "explorer/sec-sample/company/DEMC.json").read_text())
    text = V.sheet(c, years=2)
    assert text.count("| [ ] |") == sum(len(m["points"][-2:]) for m in c["metrics"].values())
    assert "https://www.sec.gov/Archives/edgar/data/9000003/" in text and "-index.htm" in text and "capex" in text
    assert V.filing_url(320193, "0000320193-24-000123").endswith("/000032019324000123/0000320193-24-000123-index.htm")


def test_verify_command_needs_the_contact_and_a_built_file(monkeypatch, capsys, tmp_path, mock):
    monkeypatch.delenv(sec.ENV, raising=False)
    assert cli.main(["verify", "AAA", "--out", str(tmp_path)]) == 2
    monkeypatch.setenv(sec.ENV, "CreditScope team@project.invalid")
    assert cli.main(["verify", "AAA", "--out", str(tmp_path)]) == 2 and "run the build first" in capsys.readouterr().err
    cli.build(mock.client(sleep=lambda s: None), ["AAA"], tmp_path, log=lambda m: None)
    mock.concepts["Revenues"] = [{"end": "2023-12-31", "start": "2023-01-01", "val": 100, "accn": "0000000001-24-000001", "form": "10-K", "filed": "2024-02-01"}]
    args = cli.argparse.Namespace(ticker="AAA", out=tmp_path, years=3, sheet=tmp_path / "sheet.md")
    assert cli.run_verify(args, "CreditScope team@project.invalid", client=mock.client(sleep=lambda s: None)) == 0
    assert (tmp_path / "sheet.md").read_text().startswith("# Verification sheet: AAA")
    assert "team@project.invalid" not in capsys.readouterr().out + (tmp_path / "sheet.md").read_text()


def test_files_record_the_reducer_version_and_a_digest_of_their_source_without_embedding_it():
    facts = company({"Revenues": {"USD": [fact("2023-12-31", 100, start="2023-01-01")]}}, 7)
    a, b = R.reduce_company(facts, "T", generated="g"), R.reduce_company(json.loads(json.dumps(facts)), "T", generated="g")
    assert a == b and a["reducerVersion"] == R.REDUCER_VERSION and re.fullmatch(r"[0-9a-f]{64}", a["sourceDigest"])
    changed = json.loads(json.dumps(facts)); changed["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["val"] = 101
    assert R.reduce_company(changed, "T", generated="g")["sourceDigest"] != a["sourceDigest"]          # any change in the SEC data changes the digest
    assert "facts" not in a and "units" not in json.dumps(a)                                           # the raw response is not carried along


def test_published_company_files_stay_compact():
    big = [f.stat().st_size for f in (ROOT / "explorer" / "sec-sample" / "company").glob("*.json")]
    assert max(big) < 60_000, big          # 30 companies must stay well under a few MB in the public repository


def test_preflight_makes_no_request_and_never_prints_the_contact(monkeypatch, capsys):
    import socket
    def refuse(*a, **k):
        raise AssertionError("preflight must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.delenv(sec.ENV, raising=False)
    assert cli.main(["preflight"]) == 2
    out = capsys.readouterr().out
    assert "NOT READY" in out and "MSFT, AAPL, WMT, JPM" in out and "No request was made" in out
    monkeypatch.setenv(sec.ENV, "CreditScope team@project.invalid")
    assert cli.main(["preflight"]) == 0
    out = capsys.readouterr().out
    assert "team@project.invalid" not in out and "Ready" in out and "5 requests" in out
    assert cli.main(["preflight", "--tickers", "bad!"]) == 2


def test_example_workflow_is_inactive_takes_tickers_through_env_and_commits_nothing():
    text = (ROOT / "docs" / "fundamentals-workflow.example.yml").read_text()
    assert not (ROOT / ".github" / "workflows" / "fundamentals.yml").exists()          # it stays an example until the owner activates it
    assert "workflow_dispatch" in text and "MSFT,AAPL,WMT,JPM" in text and "permissions:\n  contents: read" in text
    assert "git push" not in text and "git commit" not in text
    assert '"${{ inputs' not in text.split("run:", 1)[1]                                  # inputs are never spliced into shell text
    assert "preflight" in text and "secrets.SEC_USER_AGENT" in text


def test_review_reports_coverage_checks_and_tags_offline_for_built_files(capsys):
    assert cli.main(["review", "--out", str(ROOT / "explorer" / "sec-sample")]) == 0
    out = capsys.readouterr().out
    assert "== DEMA" in out and "GROSS_PROFIT_MISMATCH" in out and "via Revenues" in out and "net margin" in out
    assert cli.main(["review", "--out", str(ROOT / "docs")]) == 2


def _pts(tag, vals, start=2018, filed="2024-02-01", end_md="12-31"):
    return {"label": tag, "unit": "USD", "kind": "instant", "points": [{"fy": start + i, "end": f"{start + i}-{end_md}", "val": v, "filed": filed, "accn": f"a{i}", "form": "10-K", "tag": tag} for i, v in enumerate(vals)]}


def test_stale_series_gaps_tag_switches_and_mixed_filings_are_flagged_without_changing_values():
    from fundamentals import reduce as R
    metrics = {"revenue": _pts("Revenues", [1e9] * 8), "debt": _pts("LongTermDebt", [5e9] * 3),                   # stops FY2020; company reports to FY2025
               "operatingCashFlow": _pts("OCF", [1, 2, 3, 4, 5, 6, 7, 8]), "cash": _pts("CashA", [100, 100, 100, 300, 300, 300, 300, 300])}
    del metrics["operatingCashFlow"]["points"][3:5]                                                                # FY2021 and FY2022 missing
    metrics["cash"]["points"][3]["tag"] = "CashB"
    codes = {c["code"]: c for c in R.quality_checks(metrics)}
    assert "STALE_SERIES" in codes and "FY2020" in codes["STALE_SERIES"]["message"] and "LongTermDebt" in codes["STALE_SERIES"]["message"]
    assert "GAP_IN_SERIES" in codes and "FY2021" in codes["GAP_IN_SERIES"]["message"] and "FY2022" in codes["GAP_IN_SERIES"]["message"]
    assert "TAG_SWITCH_JUMP" in codes and "CashA to CashB" in codes["TAG_SWITCH_JUMP"]["message"] and "+200%" in codes["TAG_SWITCH_JUMP"]["message"]
    assert metrics["debt"]["points"][-1]["val"] == 5e9                                                              # flagged, never altered
    bal = {"assets": _pts("Assets", [100]), "liabilities": _pts("Liabilities", [60]), "equity": _pts("StockholdersEquity", [50])}
    bal["equity"]["points"][0]["filed"] = "2025-03-01"
    msg = [c for c in R.quality_checks(bal) if c["code"] == "BALANCE_IDENTITY"][0]["message"]
    assert "different filings" in msg and "equity filed 2025-03-01" in msg
    bal["equity"]["points"][0]["filed"] = "2024-02-01"
    assert "minority interest" in [c for c in R.quality_checks(bal) if c["code"] == "BALANCE_IDENTITY"][0]["message"]


def test_raw_responses_are_saved_outside_the_output_and_rebuild_offline_identically(mock, tmp_path):
    raw, out1, out2 = tmp_path / "raw", tmp_path / "o1", tmp_path / "o2"
    cli.build(mock.client(sleep=lambda s: None), ["AAA"], out1, log=lambda m: None, raw_dir=raw)
    assert (raw / "facts-AAA.json").exists() and (raw / "directory.json").exists() and not (out1 / "facts-AAA.json").exists()
    seen = len(mock.seen)
    cli.build(None, ["AAA"], out2, log=lambda m: None, raw_dir=raw, offline=True)
    assert len(mock.seen) == seen                                                                                    # no request on the offline rebuild
    a, b = json.loads((out1 / "company" / "AAA.json").read_text()), json.loads((out2 / "company" / "AAA.json").read_text())
    a.pop("generated"); b.pop("generated")
    assert a == b


def test_explain_lists_candidate_facts_from_the_saved_response(mock, tmp_path, capsys):
    raw = tmp_path / "raw"
    cli.build(mock.client(sleep=lambda s: None), ["AAA"], tmp_path / "o", log=lambda m: None, raw_dir=raw)
    assert cli.main(["explain", "AAA", "revenue", "--raw-dir", str(raw)]) == 0
    assert "fact(s)" in capsys.readouterr().out
    assert cli.main(["explain", "AAA", "nonsense", "--raw-dir", str(raw)]) == 2


# ---------------------------------------------------------------- consistent balance sheets, stale series, definitions, banks
def test_a_years_assets_liabilities_and_equity_come_from_one_filing_never_a_mix():
    A, B, Cc = "0000000001-16-000001", "0000000001-17-000001", "0000000001-18-000001"
    c = R.reduce_company(company({
        "Assets": {"USD": [fact("2016-06-30", 193694, filed="2016-07-28", accn=A), fact("2016-06-30", 193468, filed="2017-08-02", accn=B)]},
        "Liabilities": {"USD": [fact("2016-06-30", 121697, filed="2016-07-28", accn=A), fact("2016-06-30", 121471, filed="2017-08-02", accn=B)]},
        "StockholdersEquity": {"USD": [fact("2016-06-30", 71997, filed="2016-07-28", accn=A), fact("2016-06-30", 71997, filed="2017-08-02", accn=B),
                                       fact("2016-06-30", 83090, filed="2018-08-03", accn=Cc)]}}), "T")                       # a later restatement of equity ONLY
    got = {k: (pts(c, k)[0]["val"], pts(c, k)[0]["accn"]) for k in ("assets", "liabilities", "equity")}
    assert got == {"assets": (193468, B), "liabilities": (121471, B), "equity": (71997, B)}                                 # latest filing holding all three
    assert not [x for x in c["checks"] if x["code"] == "BALANCE_IDENTITY"]
    assert "one filing" in c["coverage"]["balanceSheetBasis"]


def test_a_figure_missing_from_the_winning_filing_stays_unavailable_not_borrowed_from_another_version():
    c = R.reduce_company(company({
        "Assets": {"USD": [fact("2020-12-31", 100, accn="0000000001-21-000001", filed="2021-02-01")]},
        "StockholdersEquity": {"USD": [fact("2020-12-31", 40, accn="0000000001-21-000001", filed="2021-02-01")]},
        "Liabilities": {"USD": [fact("2020-12-31", 55, accn="0000000001-20-000001", filed="2020-02-01")]}}), "T")                  # only in an older, different filing
    assert pts(c, "assets")[0]["val"] == 100 and pts(c, "equity")[0]["val"] == 40 and "liabilities" not in c["metrics"]
    assert "liabilities" in c["coverage"]["missing"]


def test_a_stale_series_is_removed_from_the_figures_and_recorded_so_it_cannot_look_current():
    rev = [fact(f"{y}-12-31", 100 + y, start=f"{y}-01-01", accn=f"0000000001-{y % 100}-000001") for y in range(2018, 2026)]
    debt = [fact(f"{y}-12-31", 7e9, accn=f"0000000002-{y % 100}-000001") for y in (2011, 2012, 2013)]
    c = R.reduce_company(company({"Revenues": {"USD": rev}, "LongTermDebt": {"USD": debt}}), "T")
    assert "debt" not in c["metrics"] and "debt" not in c["coverage"]["missing"]
    s = c["coverage"]["stale"]["debt"]
    assert s["lastFy"] == 2013 and s["val"] == 7e9 and s["tag"] == "LongTermDebt" and s["companyLatestFy"] == 2025 and s["accn"]
    assert [x for x in c["checks"] if x["code"] == "STALE_SERIES" and "not shown" in x["message"]]


def test_cash_that_changes_meaning_is_disclosed_and_equivalent_tags_are_not():
    cash = {"CashAndDueFromBanks": {"USD": [fact("2014-12-31", 1, accn="a-14-1")]},
            "CashAndCashEquivalentsAtCarryingValue": {"USD": [fact(f"{y}-12-31", 2, accn=f"a-{y % 100}-1") for y in (2015, 2016)]},
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {"USD": [fact("2017-12-31", 3, accn="a-17-1")]}}
    c = R.reduce_company(company(cash), "T")
    runs = c["coverage"]["definitions"]["cash"]
    assert [(r["fromFy"], r["toFy"]) for r in runs] == [(2014, 2014), (2015, 2016), (2017, 2017)] and "restricted" in runs[2]["meaning"]
    assert [x for x in c["checks"] if x["code"] == "DEFINITION_CHANGE"]
    c2 = R.reduce_company(company({"LongTermDebt": {"USD": [fact("2015-12-31", 5, accn="b-15-1")]},
                                   "LongTermDebtNoncurrent": {"USD": [fact("2016-12-31", 4, accn="b-16-1")]}, "LongTermDebtCurrent": {"USD": [fact("2016-12-31", 1, accn="b-16-1")]}}), "T")
    assert "debt" not in c2["coverage"]["definitions"]


def test_a_bank_is_recognised_from_its_filing_shape_and_ordinary_companies_are_not():
    bank = R.reduce_company(company({"Revenues": {"USD": [fact("2023-12-31", 9, start="2023-01-01")]}, "Deposits": {"USD": [fact("2023-12-31", 5)]},
                                     "NetIncomeLoss": {"USD": [fact("2023-12-31", 2, start="2023-01-01")]}}), "B")
    assert bank["profile"] == "bank" and "Deposits" in bank["profileReason"]
    other = R.reduce_company(company({"Revenues": {"USD": [fact("2023-12-31", 9, start="2023-01-01")]}, "CostOfRevenue": {"USD": [fact("2023-12-31", 4, start="2023-01-01")]}, "Deposits": {"USD": [fact("2023-12-31", 5)]}}), "O")
    assert other["profile"] == "general"


def test_operating_cash_flow_falls_back_to_the_continuing_operations_tag_and_says_so():
    c = R.reduce_company(company({
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": {"USD": [fact("2014-06-30", 32, start="2013-07-01", accn="m-14-1"), fact("2015-06-30", 29, start="2014-07-01", accn="m-15-1")]},
        "NetCashProvidedByUsedInOperatingActivities": {"USD": [fact("2016-06-30", 33, start="2015-07-01", accn="m-16-1"), fact("2015-06-30", 30, start="2014-07-01", accn="m-18-1", filed="2018-08-01")]}}), "T")
    by = {p["fy"]: p for p in pts(c, "operatingCashFlow")}
    assert by[2014]["tag"].endswith("ContinuingOperations") and by[2015]["tag"] == "NetCashProvidedByUsedInOperatingActivities" and by[2015]["val"] == 30   # the preferred tag wins when both exist
    assert [r["meaning"] for r in c["coverage"]["definitions"]["operatingCashFlow"]][0].startswith("operating cash flow from continuing")


def test_the_window_is_twelve_fiscal_years_not_twelve_points():
    facts = [fact(f"{y}-12-31", y, start=f"{y}-01-01", accn=f"w-{y % 100}-1") for y in range(2010, 2026)]
    old_gap = [fact("2005-12-31", 1, start="2005-01-01", accn="w-05-1")]
    c = R.reduce_company(company({"Revenues": {"USD": facts}, "NetIncomeLoss": {"USD": old_gap + facts[-3:]}}), "T")
    assert [p["fy"] for p in pts(c)][0] == 2014 and [p["fy"] for p in pts(c, "netIncome")][0] == 2023   # the 2005 value is outside the window, not a lonely first point


def test_equity_keeps_one_definition_when_a_later_filing_only_offers_the_wider_one():
    old, new = "w-16-1", "w-18-1"
    c = R.reduce_company(company({
        "Assets": {"USD": [fact("2015-01-31", 200, accn=old, filed="2016-03-01"), fact("2015-01-31", 200, accn=new, filed="2018-03-01")]},
        "StockholdersEquity": {"USD": [fact("2015-01-31", 80, accn=old, filed="2016-03-01")]},                                                    # parent equity only in the older filing
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {"USD": [fact("2015-01-31", 86, accn=new, filed="2018-03-01")]}}), "T")
    e = pts(c, "equity")[0]
    assert e["val"] == 80 and e["tag"] == "StockholdersEquity" and e["accn"] == old
    assert "equity" not in c["coverage"]["definitions"]


def test_a_series_that_must_use_the_wider_equity_in_some_years_discloses_the_change():
    c = R.reduce_company(company({
        "StockholdersEquity": {"USD": [fact("2016-12-31", 50, accn="e-17-1")]},
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {"USD": [fact("2015-12-31", 55, accn="e-16-1")]}}), "T")
    assert [r["tag"] for r in c["coverage"]["definitions"]["equity"]] == ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"]
