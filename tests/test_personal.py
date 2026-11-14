"""Personal edition: credentials, Alpaca client, split/dividend handling, sync, local server and repo hygiene.

No test contacts the real Alpaca service or needs real credentials: a mock server (tests/mock_alpaca.py) speaks the
documented API over real HTTP on localhost.
"""
import http.client
import json
import os
import re
import stat
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import mock_alpaca  # noqa: E402
import ref_finance as ref  # noqa: E402
from personal import build, config, credentials, service  # noqa: E402
from personal.alpaca import AlpacaError, Client  # noqa: E402
from personal.server import PersonalServer, serve_in_thread  # noqa: E402

KEY, SECRET = mock_alpaca.KEY_ID, mock_alpaca.SECRET
CREDS = credentials.Credentials(KEY, SECRET, "test")
TODAY = date(2026, 11, 14)


@pytest.fixture(autouse=True)
def private_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".creditscope"
    monkeypatch.setenv("CREDITSCOPE_HOME", str(home))
    monkeypatch.setenv("CREDITSCOPE_TODAY", TODAY.isoformat())
    monkeypatch.delenv(credentials.ENV_KEY, raising=False)
    monkeypatch.delenv(credentials.ENV_SECRET, raising=False)
    return home


@pytest.fixture
def mock():
    m = mock_alpaca.MockAlpaca(symbols={"SPY", "AAPL", "TSLA", "KO", "TLT"}, splits={"TSLA": ("2024-06-03", 4)})
    url = m.start()
    yield m, url
    m.stop()


def client(url, **kw):
    return Client(CREDS, data_url=url, trading_url=url, sleep=lambda s: None, min_interval=0, **kw)


# ---------------------------------------------------------------- credentials
def test_credentials_roundtrip_and_permissions(private_home):
    path = credentials.save(KEY, SECRET)
    assert path.parent == private_home
    loaded = credentials.load()
    assert (loaded.key_id, loaded.secret, loaded.source) == (KEY, SECRET, "file")
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_environment_variables_override_the_file(monkeypatch):
    credentials.save(KEY, SECRET)
    monkeypatch.setenv(credentials.ENV_KEY, "ENVKEYID000000")
    monkeypatch.setenv(credentials.ENV_SECRET, "ENVSECRET0000000000000")
    c = credentials.load()
    assert c.key_id == "ENVKEYID000000" and c.source == "environment"


def test_refuses_to_store_credentials_inside_a_git_repository(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("CREDITSCOPE_HOME", str(repo / "private"))
    with pytest.raises(credentials.CredentialError, match="git working tree"):
        credentials.save(KEY, SECRET)
    assert not (repo / "private").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_loose_permissions_are_tightened_on_load():
    path = credentials.save(KEY, SECRET)
    os.chmod(path, 0o644)
    credentials.load()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_secret_never_appears_in_repr_str_or_errors(private_home):
    c = credentials.Credentials(KEY, SECRET)
    assert SECRET not in repr(c) and SECRET not in str(c) and "***" in repr(c)
    private_home.mkdir(parents=True)
    (private_home / "credentials.json").write_text("{not json " + SECRET)
    with pytest.raises(credentials.CredentialError) as err:
        credentials.load()
    assert SECRET not in str(err.value)


@pytest.mark.parametrize("key,secret", [("", SECRET), (KEY, ""), ("short", SECRET), (KEY, "tooshort"), ("has space 123456", SECRET), (KEY, SECRET + "\n x")])
def test_bad_credentials_are_rejected_and_not_saved(key, secret, private_home):
    with pytest.raises(credentials.CredentialError):
        credentials.save(key, secret)
    assert not (private_home / "credentials.json").exists()


def test_missing_credentials_message_and_forget():
    with pytest.raises(credentials.CredentialError, match="setup"):
        credentials.load()
    credentials.save(KEY, SECRET)
    assert credentials.forget() is True and credentials.forget() is False


# ---------------------------------------------------------------- Alpaca client
def test_bars_use_split_adjustment_and_follow_pagination(mock):
    m, url = mock
    m.page_size = 400
    bars = client(url).bars(["SPY"], "2021-11-01", "2026-11-13", adjustment="split", feed="sip")
    assert len(bars["SPY"]) == len(m.series["SPY"]["dates"])
    calls = [c for c in m.calls if c[0] == "/v2/stocks/bars"]
    assert len(calls) >= 3 and all(c[1]["adjustment"] == "split" and c[1]["feed"] == "sip" for c in calls)
    assert all(int(c[1]["limit"]) <= 10000 for c in calls)


def test_credentials_travel_only_in_headers(mock):
    m, url = mock
    client(url).bars(["SPY"], "2026-10-01", "2026-11-13")
    path, query, headers = m.calls[-1]
    headers = {k.lower(): v for k, v in headers.items()}                  # HTTP header names are case-insensitive
    assert headers["apca-api-key-id"] == KEY and headers["apca-api-secret-key"] == SECRET
    assert SECRET not in path and SECRET not in json.dumps(query) and KEY not in json.dumps(query)


def test_wrong_credentials_give_a_clear_error_without_leaking(mock):
    m, url = mock
    bad = Client(credentials.Credentials("WRONGKEYID000000", "WRONGSECRET000000000000"), data_url=url, trading_url=url, sleep=lambda s: None, min_interval=0)
    with pytest.raises(AlpacaError) as err:
        bad.account()
    assert err.value.status == 401 and "credentials" in str(err.value) and "WRONGSECRET" not in str(err.value)


def test_rate_limit_is_retried_using_the_reset_header(mock):
    m, url = mock
    m.rate_limit_left = 2
    slept = []
    c = Client(CREDS, data_url=url, trading_url=url, sleep=slept.append, min_interval=0)
    assert c.account()["status"] == "ACTIVE"
    assert len(slept) == 2 and all(s >= 1.0 for s in slept)


def test_persistent_rate_limit_fails_clearly(mock):
    m, url = mock
    m.rate_limit_left = 99
    c = Client(CREDS, data_url=url, trading_url=url, sleep=lambda s: None, min_interval=0, max_retries=2)
    with pytest.raises(AlpacaError, match="429"):
        c.account()


def test_iex_only_account_cannot_read_sip(mock):
    m, url = mock
    m.iex_only = True
    with pytest.raises(AlpacaError) as err:
        client(url).bars(["SPY"], "2026-10-01", "2026-11-01", feed="sip")
    assert err.value.status == 403
    assert client(url).bars(["SPY"], "2026-10-01", "2026-11-01", feed="iex")["SPY"]


def test_corporate_actions_parse_dividends_and_split_ratios(mock):
    m, url = mock
    ca = client(url).corporate_actions(["TSLA", "SPY"], "2021-01-01", "2026-12-31")
    assert ca["splits"]["TSLA"] == [{"ex_date": "2024-06-03", "ratio": 4.0}]
    assert len(ca["dividends"]["SPY"]) == len(m.series["SPY"]["dividends"]) and ca["dividends"]["TSLA"] == []


# ---------------------------------------------------------------- split / dividend logic
def test_dividends_are_divided_by_later_splits_only():
    divs = [{"ex_date": "2020-01-10", "rate": 1.0}, {"ex_date": "2021-01-10", "rate": 0.5}, {"ex_date": "2023-01-10", "rate": 0.2}]
    splits = [{"ex_date": "2020-06-01", "ratio": 4.0}, {"ex_date": "2022-06-01", "ratio": 0.5}]       # 4-for-1, then 1-for-2 reverse
    # 2020 dividend: both splits come later (4 then 0.5, product 2) -> 0.5; 2021: only the reverse split is later -> /0.5 = 1.0; 2023: none
    assert build.adjusted_dividends(divs, splits) == [["2020-01-10", 0.5], ["2021-01-10", 1.0], ["2023-01-10", 0.2]]
    assert build.adjusted_dividends([{"ex_date": "2020-01-10", "rate": 0.73}], [{"ex_date": "2020-08-31", "ratio": 4}]) == [["2020-01-10", 0.1825]]
    assert build.adjusted_dividends([], splits) == [] and build.adjusted_dividends([{"ex_date": None, "rate": 1}, {"ex_date": "2020-01-01", "rate": None}], []) == []


def test_make_series_shapes_dedupes_and_requires_two_bars():
    bars = [{"t": "2026-11-12T05:00:00Z", "c": "10.5", "v": 100}, {"t": "2026-11-13T05:00:00Z", "c": 11, "v": None},
            {"t": "2026-11-12T05:00:00Z", "c": 10.6, "v": 120}, {"bad": 1}]
    s = build.make_series("ABC", bars, None, [], {"name": "ABC Corp", "t": "S", "exchange": "NYSE", "feed": "sip"})
    assert s["dates"] == ["2026-11-12", "2026-11-13"] and s["close"] == [10.6, 11.0] and s["volume"] == [120, 0]
    assert s["dividends"] is None and s["synthetic"] is False and s["type"] == "Stock"
    assert build.make_series("ABC", bars[:1], None, [], {}) is None
    assert build.make_series("ABC", bars, [], [], {})["dividends"] == []


def test_merge_series_overlays_and_unions_dividends():
    old = {"dates": ["d1", "d2"], "close": [1, 2], "volume": [10, 20], "dividends": [["d1", 0.1]]}
    new = {"dates": ["d2", "d3"], "close": [2.5, 3], "volume": [25, 30], "dividends": [["d1", 0.1], ["d3", 0.2]], "name": "n"}
    m = build.merge_series(old, new)
    assert m["dates"] == ["d1", "d2", "d3"] and m["close"] == [1, 2.5, 3] and m["dividends"] == [["d1", 0.1], ["d3", 0.2]]
    assert build.merge_series(old, dict(new, dividends=None))["dividends"] == [["d1", 0.1]]


def test_etf_guess_index_and_window():
    assert build.guess_type("SPDR S&P 500 ETF Trust") == "E" and build.guess_type("iShares 20+ Year Treasury Bond ETF") == "E"
    assert build.guess_type("Apple Inc. Common Stock") == "S" and build.guess_type("Invesco QQQ Trust, Series 1") == "E"
    idx = build.build_index([{"symbol": "SPY", "name": "SPDR S&P 500 ETF", "exchange": "ARCA", "tradable": True},
                             {"symbol": "ZZZ", "name": "Dead", "tradable": False}, {"symbol": "A B", "name": "bad"},
                             {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "tradable": True}], ["AAPL", "SPY"], "iex", "2026-11-13", ["SPY"])
    assert [e["s"] for e in idx["entries"]] == ["AAPL", "SPY"] and idx["entries"][0]["r"] == 1 and idx["meta"]["feed"] == "iex" and idx["meta"]["private"] is True
    start, end = build.date_window(10, date(2026, 11, 14))
    assert end == "2026-11-13" and start == "2016-11-06"


# ---------------------------------------------------------------- sync end to end (mock Alpaca over HTTP)
def test_detect_feed(mock):
    m, url = mock
    assert service.detect_feed(client(url))[0] == "sip"
    m.iex_only = True
    feed, note = service.detect_feed(client(url))
    assert feed == "iex" and "IEX-only" in note


def sync(url, symbols, tmp_data):
    return service.full_sync(client(url), symbols, tmp_data, years=10)


def test_full_sync_rebuilds_the_sample_exactly_including_split_adjustment(mock, private_home):
    m, url = mock
    data = config.data_dir()
    res = sync(url, ["SPY", "AAPL", "TSLA", "KO"], data)
    assert sorted(res["written"]) == ["AAPL", "KO", "SPY", "TSLA"] and res["feed"] == "sip"
    for sym in res["written"]:
        got, want = build.read_series(data, sym), m.series[sym]
        assert got["dates"] == want["dates"] and got["volume"] == want["volume"] and got["close"] == pytest.approx(want["close"])
        assert got["synthetic"] is False and got["feed"] == "sip"
        if want["dividends"] is None:
            assert got["dividends"] == []                   # Alpaca returned no rows: known-none vs unknown cannot be told apart
        else:
            assert [d[0] for d in got["dividends"]] == [d[0] for d in want["dividends"]]
            assert [d[1] for d in got["dividends"]] == pytest.approx([d[1] for d in want["dividends"]], abs=1e-6)   # TSLA: split-adjusted back
    index = json.loads((data / "index.json").read_text())
    assert index["meta"]["asOf"] == "2026-11-13" and index["meta"]["private"] and len(index["entries"]) >= 5
    assert "ZZZ" not in [e["s"] for e in index["entries"]]


def test_iex_account_is_labelled_and_volume_is_iex_only(mock):
    m, url = mock
    m.iex_only = True
    data = config.data_dir()
    res = sync(url, ["SPY"], data)
    s = build.read_series(data, "SPY")
    assert res["feed"] == "iex" and s["feed"] == "iex" and s["volume"][0] < m.series["SPY"]["volume"][0]


def test_unknown_symbol_is_skipped_not_fatal(mock):
    m, url = mock
    res = sync(url, ["SPY", "NOPE"], config.data_dir())
    assert res["written"] == ["SPY"] and "NOPE" in res["skipped"]


def test_dividend_cross_check_passes_for_correct_data_and_flags_wrong_amounts(mock):
    m, url = mock
    c = client(url)
    ok = service.verify_dividends(c, "SPY", "2021-11-15", "2026-11-13", "sip")
    assert len(ok) >= 10 and all(r["ok"] for r in ok)
    tsla = service.verify_dividends(c, "TSLA", "2021-11-15", "2026-11-13", "sip")
    assert tsla == []                                         # TSLA pays no dividends in the sample
    m.listed_scale = 3.0                                      # corporate-actions now lists 3x amounts; the dividend-adjusted bars are unchanged
    bad = service.verify_dividends(c, "SPY", "2021-11-15", "2026-11-13", "sip")
    assert bad and not any(r["ok"] for r in bad)


def test_series_built_from_alpaca_data_give_the_same_analytics_as_the_python_reference(mock):
    """bars -> series -> independent Python calculations equal the committed expected results for the same securities."""
    m, url = mock
    data = config.data_dir()
    sync(url, ["SPY", "AAPL", "TSLA"], data)
    expected = json.loads((ROOT / "tests/fixtures/explorer_expected.json").read_text())["summaries"]
    spy = build.read_series(data, "SPY")
    for sym in ("AAPL", "TSLA"):
        s = build.read_series(data, sym)
        if m.series[sym]["dividends"] is None:
            continue
        for period in ref.PERIODS:
            got = ref.summarize(s, period, spy)
            want = expected[sym][period]
            for k in ("cumulativeReturn", "volatility", "annualizedReturn"):
                if want.get(k) is None:
                    assert got.get(k) is None
                else:
                    assert got[k] == pytest.approx(want[k], rel=1e-6, abs=1e-9), f"{sym}/{period}/{k}"


def test_cached_series_respects_age(mock):
    m, url = mock
    data = config.data_dir()
    sync(url, ["SPY"], data)
    assert service.cached_series(data, "SPY") is not None
    old = build.series_path(data, "SPY")
    os.utime(old, (1, 1))
    assert service.cached_series(data, "SPY") is None and service.cached_series(data, "NOPE") is None


# ---------------------------------------------------------------- local server
def request(server, path, host=None, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    conn.request(method, path, headers={"Host": host if host is not None else f"localhost:{server.server_address[1]}"})
    r = conn.getresponse()
    body = r.read()
    headers = {k.lower(): v for k, v in r.getheaders()}
    conn.close()
    return r.status, headers, body


@pytest.fixture
def served(mock, tmp_path):
    m, url = mock
    data = config.data_dir()
    sync(url, ["SPY"], data)
    holder = {}
    server = PersonalServer("127.0.0.1", 0, ROOT, data,
                            client_factory=lambda: holder.setdefault("c", client(url)), feed=lambda: "sip")
    serve_in_thread(server)
    yield server, m
    server.shutdown()
    server.server_close()


def test_server_only_binds_to_loopback(tmp_path):
    for host in ("0.0.0.0", "192.168.1.5", ""):
        with pytest.raises(ValueError, match="loopback"):
            PersonalServer(host, 0, ROOT, tmp_path)


def test_server_serves_site_and_private_data_with_no_store(served):
    s, _ = served
    st, h, body = request(s, "/explorer.html")
    assert st == 200 and b"Stock Explorer" in body and h["x-content-type-options"] == "nosniff"
    assert b'name="creditscope-personal"' in body                              # marker that makes the page look for private data
    assert b"creditscope-personal" not in request(s, "/index.html")[2]
    assert b"creditscope-personal" not in (ROOT / "explorer.html").read_bytes()  # the public file never carries it
    st, h, body = request(s, "/private-data/index.json")
    assert st == 200 and h["cache-control"] == "no-store" and json.loads(body)["meta"]["private"] is True
    st, h, body = request(s, "/private-data/series/SPY.json")
    assert st == 200 and h["cache-control"] == "no-store" and json.loads(body)["symbol"] == "SPY"
    st, h, body = request(s, "/assets/js/finance.js")
    assert st == 200 and b"Finance" in body


@pytest.mark.parametrize("path", ["/.git/config", "/.git/HEAD", "/personal/credentials.py", "/personal/server.py", "/tests/mock_alpaca.py",
                                  "/docs/explorer-data-sources.md", "/creditscope/run.py", "/.gitignore", "/README.md", "/data/raw/", "/requirements-dev.txt"])
def test_server_does_not_expose_source_git_or_unlisted_files(served, path):
    s, _ = served
    assert request(s, path)[0] in (404, 400)


@pytest.mark.parametrize("path", ["/../personal/credentials.py", "/assets/../personal/credentials.py", "/%2e%2e/personal/credentials.py",
                                  "/assets/%2e%2e/%2e%2e/.git/config", "/private-data/../credentials.json", "/private-data/series/../../credentials.json",
                                  "/private-data/series/%2e%2e%2fcredentials.json", "/private-data/credentials.json", "/api/series/../../credentials",
                                  "/private-data/series/SPY.json%00.txt"])
def test_path_traversal_is_blocked(served, path):
    s, _ = served
    st, _, body = request(s, path)
    assert st in (400, 404) and b"TESTSECRET" not in body


def test_host_header_must_be_loopback(served):
    s, _ = served
    port = s.server_address[1]
    assert request(s, "/api/health", host=f"localhost:{port}")[0] == 200
    assert request(s, "/api/health", host=f"127.0.0.1:{port}")[0] == 200
    for bad in ("evil.example.com", f"evil.example.com:{port}", "localhost.evil.com", "192.168.0.10:8765", ""):
        assert request(s, "/private-data/index.json", host=bad)[0] == 403


def test_api_series_cached_on_demand_invalid_and_errors(served):
    s, m = served
    assert request(s, "/api/series/SPY")[0] == 200                           # synced and fresh
    st, _, body = request(s, "/api/series/AAPL")                              # not synced: fetched through the (mock) Alpaca API
    assert st == 200 and json.loads(body)["symbol"] == "AAPL" and (config.data_dir() / "series" / "AAPL.json").exists()
    assert request(s, "/api/series/aapl")[0] == 200                           # case-insensitive
    assert request(s, "/api/series/BAD%20SYMBOL%21")[0] == 400 and request(s, "/api/series/" + "A" * 40)[0] == 400
    assert request(s, "/api/series/NOPE")[0] == 404
    m.require_auth = True
    s.client_factory = lambda: Client(credentials.Credentials("WRONGKEYID000000", "WRONGSECRET000000000000"), data_url=f"http://127.0.0.1:{m.httpd.server_address[1]}",
                                      trading_url=f"http://127.0.0.1:{m.httpd.server_address[1]}", sleep=lambda x: None, min_interval=0)
    st, _, body = request(s, "/api/series/KO")
    assert st == 502 and b"credentials" in body and b"WRONGSECRET" not in body
    s.client_factory = lambda: None
    st, _, body = request(s, "/api/series/TLT")
    assert st == 404 and b"setup" in body


def test_stale_copy_is_served_when_alpaca_cannot_be_reached(served):
    s, m = served
    path = build.series_path(config.data_dir(), "SPY")
    os.utime(path, (1, 1))                                                    # make the cached SPY copy stale
    s.client_factory = lambda: None                                            # no credentials: cannot refresh
    st, _, body = request(s, "/api/series/SPY")
    assert st == 200 and json.loads(body)["symbol"] == "SPY"
    s.client_factory = lambda: Client(credentials.Credentials("WRONGKEYID000000", "WRONGSECRET000000000000"), data_url=f"http://127.0.0.1:{m.httpd.server_address[1]}",
                                      trading_url=f"http://127.0.0.1:{m.httpd.server_address[1]}", sleep=lambda x: None, min_interval=0)
    st, _, body = request(s, "/api/series/SPY")                               # refresh fails (401): still serve the stale copy, not an error
    assert st == 200 and b"WRONGSECRET" not in body
    assert request(s, "/api/series/NOSUCH")[0] == 502                         # nothing cached and the fetch fails


def test_no_response_ever_contains_the_credentials(served):
    s, _ = served
    for path in ("/explorer.html", "/private-data/index.json", "/api/series/SPY", "/api/health", "/sw.js", "/nope"):
        _, h, body = request(s, path)
        blob = body + json.dumps(h).encode()
        assert SECRET.encode() not in blob and KEY.encode() not in blob


# ---------------------------------------------------------------- repository hygiene
def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def tracked():
    return [f for f in git("ls-files").stdout.splitlines() if (ROOT / f).is_file()]


@pytest.mark.parametrize("name", [".env", ".env.local", "private/x.json", "private-data/index.json", "credentials.json",
                                  "credentials.local.json", ".creditscope/credentials.json", "alpaca.pem", "secrets/key.txt"])
def test_private_paths_are_gitignored(name):
    assert git("check-ignore", "-q", name).returncode == 0, name + " is not ignored"


def test_no_credential_or_private_data_files_are_tracked():
    bad = [f for f in tracked() if re.search(r"(^|/)(\.env(\..*)?|credentials.*\.json|.*\.pem|.*\.key)$", f) or f.startswith(("private/", "private-data/", ".creditscope/"))]
    assert bad == []


SECRET_PATTERNS = [
    (re.compile(r"\b(PK|AK|CK)[A-Z0-9]{18,20}\b"), "Alpaca-style key id"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"""(?i)(secret|api[_-]?key|token|password)\s*[:=]\s*["'][A-Za-z0-9/+_\-]{24,}["']"""), "long credential literal"),
]


def test_no_secret_like_strings_in_tracked_files():
    hits = []
    for f in tracked():
        if f.endswith((".png", ".gz", ".ico", ".pdf")) or f.startswith("data/raw/") or "chart.umd" in f:
            continue
        try:
            text = (ROOT / f).read_text(errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "TESTKEY" in line or "TESTSECRET" in line or "WRONGSECRET" in line or "ENVSECRET" in line:
                continue                                                  # deliberate fake test values
            for rx, label in SECRET_PATTERNS:
                if rx.search(line):
                    hits.append(f"{f}:{lineno} {label}")
    assert hits == []


def test_public_workflows_and_site_never_reference_private_locations():
    for wf in (ROOT / ".github/workflows").glob("*.yml"):
        text = wf.read_text()
        assert not re.search(r"private-data|\.creditscope|personal/|ALPACA|credentials", text), wf.name
    for page in ("index.html", "browse.html", "trends.html", "explorer.html"):
        assert "ALPACA" not in (ROOT / page).read_text().upper().replace("ALPACA (PERSONAL", "")   # no provider keys or branding leak into pages


def test_default_private_home_is_outside_the_repository(monkeypatch):
    monkeypatch.delenv("CREDITSCOPE_HOME", raising=False)
    home = config.home().resolve()
    assert ROOT.resolve() not in [home, *home.parents]


def test_explorer_only_probes_private_data_on_localhost_and_service_worker_skips_it():
    js = (ROOT / "assets/js/explorer.js").read_text()
    assert "private-data/" in js and re.search(r"localhost|127\.0\.0\.1", js)
    sw = (ROOT / "sw.js").read_text()
    assert "private-data/" in sw and "api/" in sw                              # never cached by the service worker


# ---------------------------------------------------------------- command line (real entry points, mock Alpaca over HTTP)
from personal import __main__ as cli  # noqa: E402


@pytest.fixture
def cli_env(monkeypatch):
    m = mock_alpaca.MockAlpaca(filler_assets=600)
    url = m.start()
    monkeypatch.setenv("ALPACA_DATA_URL", url)
    monkeypatch.setenv("ALPACA_TRADING_URL", url)
    monkeypatch.setattr("time.sleep", lambda s: None)
    yield m
    m.stop()


def run_cli(*args):
    return cli.main(list(args))


def test_cli_setup_prompts_hidden_saves_privately_and_never_echoes(monkeypatch, capsys, private_home):
    answers = iter([KEY, SECRET])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    assert run_cli("setup") == 0
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err and KEY not in out.out + out.err
    assert credentials.load().secret == SECRET


def test_cli_setup_rejects_bad_input_and_repo_locations(monkeypatch, capsys, tmp_path):
    answers = iter(["x", "y"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    assert run_cli("setup") == 2 and "Not saved" in capsys.readouterr().err
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("CREDITSCOPE_HOME", str(repo / "p"))
    assert run_cli("setup") == 2 and "outside" in capsys.readouterr().err


def test_cli_doctor_sync_status_forget_flow(cli_env, monkeypatch, capsys, private_home):
    monkeypatch.setenv(credentials.ENV_KEY, KEY)
    monkeypatch.setenv(credentials.ENV_SECRET, SECRET)
    assert run_cli("doctor", "--verify-dividends") == 0
    out = capsys.readouterr().out
    assert "data feed: SIP" in out and "dividends cross-checked" in out and "All checks passed" in out
    assert SECRET not in out and KEY not in out
    assert run_cli("sync", "SPY", "AAPL") == 0
    out = capsys.readouterr().out
    assert "Wrote 2 series" in out and "outside the repository" in out and SECRET not in out
    assert run_cli("status") == 0 and "2 series" in capsys.readouterr().out
    assert (config.data_dir() / "series" / "SPY.json").exists()


def test_cli_doctor_reports_wrong_credentials_without_leaking(cli_env, monkeypatch, capsys):
    monkeypatch.setenv(credentials.ENV_KEY, "WRONGKEYID000000")
    monkeypatch.setenv(credentials.ENV_SECRET, "WRONGSECRET000000000000")
    assert run_cli("doctor") == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "401" in out and "WRONGSECRET" not in out


def test_cli_doctor_without_credentials_and_invalid_sync_symbols(capsys):
    assert run_cli("doctor") == 1 and "setup" in capsys.readouterr().out
    assert run_cli("sync", "BAD SYMBOL") == 2


def test_cli_doctor_labels_an_iex_only_account(cli_env, monkeypatch, capsys):
    cli_env.iex_only = True
    monkeypatch.setenv(credentials.ENV_KEY, KEY)
    monkeypatch.setenv(credentials.ENV_SECRET, SECRET)
    assert run_cli("doctor") == 0
    assert "data feed: IEX" in capsys.readouterr().out
