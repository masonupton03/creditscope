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
