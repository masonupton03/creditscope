"""Private storage of the portfolio ledger and its localhost API: validation, atomic writes, permissions, revisions,
cross-site protection, and proof that nothing about holdings reaches the repository or the public site."""
import http.client
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from personal import build, config, portfolio  # noqa: E402
from personal.server import PersonalServer, serve_in_thread  # noqa: E402

GOOD = {"version": 1, "baseCurrency": "USD", "benchmark": "SPY", "transactions": [
    {"id": "t1", "date": "2024-01-02", "type": "deposit", "amount": 1000},
    {"id": "t2", "date": "2024-01-03", "type": "buy", "symbol": "VTI", "shares": 2.5, "price": 230.5, "fee": 0, "external": False}]}


@pytest.fixture(autouse=True)
def private_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".creditscope"
    monkeypatch.setenv("CREDITSCOPE_HOME", str(home))
    return home


@pytest.fixture
def served(tmp_path):
    server = PersonalServer("127.0.0.1", 0, ROOT, tmp_path / "data")
    serve_in_thread(server)
    yield server
    server.shutdown()
    server.server_close()


def call(server, method, path="/api/portfolio", body=None, headers=None, host=None):
    port = server.server_address[1]
    h = {"Host": host or f"localhost:{port}"}
    if body is not None:
        h.update({"Content-Type": "application/json", "X-CreditScope": "1"})
    h.update(headers or {})
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    raw = r.read()
    out = (r.status, {k.lower(): v for k, v in r.getheaders()}, raw)
    conn.close()
    return out


def put(server, portfolio_obj, rev, **kw):
    return call(server, "PUT", body={"baseRevision": rev, "portfolio": portfolio_obj}, **kw)


# ------------------------------------------------------------ validation
@pytest.mark.parametrize("mutate, fragment", [
    (lambda p: p["transactions"][0].update(date="2024-02-30"), "real YYYY-MM-DD"),
    (lambda p: p["transactions"][0].update(type="gift"), "type must be"),
    (lambda p: p["transactions"][0].update(amount=-1), "amount must be positive"),
    (lambda p: p["transactions"][0].update(amount=float("nan")), "amount must be positive"),
    (lambda p: p["transactions"][1].update(symbol="vti"), "symbol must look like"),
    (lambda p: p["transactions"][1].update(shares=0), "shares must be positive"),
    (lambda p: p["transactions"][1].update(price="9"), "price must be positive"),
    (lambda p: p["transactions"][1].update(fee=-1), "fee must be zero"),
    (lambda p: p["transactions"][1].update(external="yes"), "external must be"),
    (lambda p: p["transactions"][1].update(id="t1"), "id must be unique"),
    (lambda p: p["transactions"][1].update(note="x" * 201), "note must be"),
    (lambda p: p.update(version=2), "version must be 1"),
    (lambda p: p.update(benchmark="not a ticker!"), "benchmark"),
])
def test_validation_rejects_bad_ledgers(mutate, fragment):
    p = json.loads(json.dumps(GOOD))
    mutate(p)
    assert any(fragment in e for e in portfolio.validate(p)), portfolio.validate(p)


def test_validation_accepts_a_good_ledger_and_rejects_non_objects():
    assert portfolio.validate(GOOD) == []
    for bad in (None, [], "x", {"version": 1}, {"version": 1, "transactions": "no"}):
        assert portfolio.validate(bad)
    assert portfolio.validate({"version": 1, "transactions": [GOOD["transactions"][0]] * 5001})


# ------------------------------------------------------------ storage
def test_save_load_permissions_backup_and_revisions(private_home):
    obj, rev = portfolio.load()
    assert rev == "new" and obj["transactions"] == []
    rev1 = portfolio.save(GOOD, "new")
    f = portfolio.path()
    assert f.parent == private_home and stat.S_IMODE(f.stat().st_mode) == 0o600 and stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert portfolio.load()[1] == rev1 and portfolio.load()[0] == GOOD
    changed = json.loads(json.dumps(GOOD)); changed["transactions"].append({"date": "2024-02-01", "type": "fee", "amount": 3})
    rev2 = portfolio.save(changed, rev1)
    bak = f.with_name(f.name + ".bak")
    assert json.loads(bak.read_text()) == GOOD and stat.S_IMODE(bak.stat().st_mode) == 0o600
    with pytest.raises(portfolio.Conflict):
        portfolio.save(GOOD, rev1)                              # stale revision
    with pytest.raises(portfolio.Conflict):
        portfolio.save(GOOD, "new")                             # file exists now
    assert portfolio.load()[1] == rev2 and not list(private_home.glob("*.tmp"))


def test_invalid_writes_leave_the_file_untouched(private_home):
    rev = portfolio.save(GOOD, "new")
    before = portfolio.path().read_bytes()
    with pytest.raises(portfolio.Invalid):
        portfolio.save({"version": 1, "transactions": [{"date": "x", "type": "buy"}]}, rev)
    assert portfolio.path().read_bytes() == before


def test_corrupt_or_oversized_files_are_reported_not_crashed(private_home):
    private_home.mkdir(parents=True)
    portfolio.path().write_text("{not json")
    with pytest.raises(portfolio.Invalid):
        portfolio.load()
    portfolio.path().write_bytes(b" " * (portfolio.MAX_BYTES + 1))
    with pytest.raises(portfolio.Invalid):
        portfolio.load()


def test_refuses_to_store_inside_a_git_repository(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("CREDITSCOPE_HOME", str(repo / "private"))
    with pytest.raises(portfolio.Invalid):
        portfolio.save(GOOD, "new")


# ------------------------------------------------------------ the API
def test_api_roundtrip_is_no_store_and_never_logged(served, private_home, capfd):
    s, h, b = call(served, "GET")
    assert s == 200 and h["cache-control"] == "no-store" and json.loads(b)["revision"] == "new"
    s, h, b = put(served, GOOD, "new")
    assert s == 200 and h["cache-control"] == "no-store"
    rev = json.loads(b)["revision"]
    s, _, b = call(served, "GET")
    assert json.loads(b) == {"portfolio": GOOD, "revision": rev}
    out = capfd.readouterr()
    assert "VTI" not in out.out + out.err and "230.5" not in out.out + out.err


def test_api_validation_conflict_and_malformed_bodies(served):
    rev = json.loads(put(served, GOOD, "new")[2])["revision"]
    s, _, b = put(served, {"version": 1, "transactions": [{"date": "2024-13-01", "type": "deposit", "amount": 1}]}, rev)
    assert s == 422 and "real YYYY-MM-DD" in json.loads(b)["details"][0]
    assert put(served, GOOD, "stale")[0] == 409
    assert call(served, "PUT", body=b"not json")[0] == 400
    assert call(served, "PUT", body={"portfolio": GOOD})[0] == 400                       # no baseRevision
    assert call(served, "PUT", body={"baseRevision": 5, "portfolio": GOOD})[0] == 400
    big = b'{"baseRevision":"x","portfolio":"' + b"a" * (portfolio.MAX_BYTES + 10) + b'"}'
    try:
        assert call(served, "PUT", body=big)[0] == 413
    except (BrokenPipeError, ConnectionResetError):          # the server may close before the client finishes sending 1 MB: also a refusal
        pass
    assert call(served, "PUT", path="/api/other", body={})[0] == 404
    assert json.loads(call(served, "GET")[2])["revision"] == rev                          # nothing above changed it


def test_api_blocks_cross_site_and_rebinding_requests(served):
    assert put(served, GOOD, "new", host="evil.example")[0] == 403                          # DNS rebinding
    assert call(served, "GET", host="evil.example")[0] == 403
    assert put(served, GOOD, "new", headers={"Origin": "http://evil.example"})[0] == 403    # another site's page
    assert put(served, GOOD, "new", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert call(served, "GET", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    port = served.server_address[1]
    assert put(served, GOOD, "new", headers={"Origin": f"http://localhost:{port}"})[0] == 200
    plain = call(served, "PUT", body=json.dumps({"baseRevision": "x", "portfolio": GOOD}).encode(),
                 headers={"Content-Type": "text/plain", "X-CreditScope": "1"})
    assert plain[0] == 400                                                                   # simple cross-site form posts
    missing = call(served, "PUT", body=json.dumps({"baseRevision": "x", "portfolio": GOOD}).encode(),
                   headers={"Content-Type": "application/json", "X-CreditScope": ""})
    assert missing[0] == 400


def test_portfolio_page_is_marked_personal_only_by_the_personal_server(served):
    s, _, b = call(served, "GET", path="/portfolio.html")
    assert s == 200 and b'name="creditscope-personal"' in b
    assert b'name="creditscope-personal"' not in (ROOT / "portfolio.html").read_bytes()


# ------------------------------------------------------------ nothing private in the repository or public site
def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    return [f for f in out if f]


def test_no_portfolio_data_files_are_tracked_and_the_name_is_ignored():
    assert not [f for f in tracked() if re.search(r"(^|/)portfolio[^/]*\.json(\.bak)?$", f) and not f.startswith("explorer/sample/")
                and not f.startswith("tests/")]
    assert subprocess.run(["git", "check-ignore", "-q", "private/portfolio.json"], cwd=ROOT).returncode == 0
    assert subprocess.run(["git", "check-ignore", "-q", "portfolio.json.bak"], cwd=ROOT).returncode == 0


def test_page_code_has_no_browser_storage_for_holdings():
    for f in ("assets/js/portfolio.js", "assets/js/portfolio-page.js"):
        text = (ROOT / f).read_text()
        assert not re.search(r"localStorage|sessionStorage|indexedDB|document\.cookie", text), f


def test_service_worker_never_caches_the_portfolio_api_or_files():
    sw = (ROOT / "sw.js").read_text()
    assert "api/" in sw and "private-data/" in sw
    assert not re.search(r"(?<!sample/)portfolio\.json|api/portfolio", sw.split("const SHELL")[1].split("];")[0])


def test_alpaca_series_carry_splits_for_the_dashboard():
    bars = [{"t": "2024-06-0%dT04:00:00Z" % d, "c": 100.0 + d, "v": 10} for d in range(3, 8)]
    s = build.make_series("X", bars, [], [{"ex_date": "2024-06-03", "ratio": 4}], {"name": "X"})
    assert s["splits"] == [("2024-06-03", 4.0)] or s["splits"] == [["2024-06-03", 4.0]]
    assert build.make_series("X", bars, [], None, {"name": "X"})["splits"] is None
