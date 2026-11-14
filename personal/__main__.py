"""Personal edition command line.

    python -m personal setup            store your Alpaca key (hidden prompts; saved outside the repository, mode 0600)
    python -m personal doctor           check what your account can access (feed, history depth, dividends, ETFs)
    python -m personal sync [SYMBOLS]   download 10 years of daily history for your universe (default list or SYMBOLS)
    python -m personal serve            open the site with your private data at http://localhost:8765/explorer.html
    python -m personal status | forget
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import date, timedelta

from . import build, config, credentials, service
from .alpaca import AlpacaError, Client
from .server import PersonalServer


def _client() -> Client:
    return Client(credentials.load())


def cmd_setup(args) -> int:
    if config.inside_git_repo(config.home()):
        print("CREDITSCOPE_HOME points inside a git repository. Choose a folder outside it.", file=sys.stderr)
        return 2
    print("Enter your Alpaca PAPER API key. Input is hidden and is never printed or sent anywhere except to Alpaca.")
    try:
        key = getpass.getpass("API key ID: ").strip()
        secret = getpass.getpass("Secret key: ").strip()
        path = credentials.save(key, secret)
    except credentials.CredentialError as e:
        print("Not saved:", e, file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. Nothing was saved.", file=sys.stderr)
        return 130
    print(f"Saved to {path} (owner-only permissions). Next: python -m personal doctor")
    return 0


def cmd_doctor(args) -> int:
    ok = True

    def line(good: bool, text: str):
        nonlocal ok
        ok = ok and good
        print(("  OK   " if good else "  FAIL ") + text)

    try:
        creds = credentials.load()
        line(True, f"credentials found ({creds.source}), key id {credentials.redact(creds.key_id)}")
    except credentials.CredentialError as e:
        line(False, str(e))
        return 1
    client = Client(creds)
    try:
        acct = client.account()
        line(acct.get("status") == "ACTIVE", f"account status: {acct.get('status')}")
    except AlpacaError as e:
        line(False, "account check: " + str(e))
        return 1
    try:
        assets = client.assets()
        symbols = {a.get("symbol") for a in assets}
        line(len(assets) > 500, f"{len(assets)} active US equity assets listed")
        line("SPY" in symbols and "QQQ" in symbols, "ETFs such as SPY and QQQ appear in the asset list: " + str("SPY" in symbols and "QQQ" in symbols))
        feed, note = service.detect_feed(client)
        line(True, f"data feed: {feed.upper()}. {note}")
        data = client.bars(["SPY"], "2016-01-01", (config.today() - timedelta(days=5)).isoformat(), adjustment="split", feed=feed)["SPY"]
        line(len(data) >= 1000, f"SPY daily history: {len(data)} bars, earliest {build.bar_date(data[0]) if data else 'n/a'}")
        raw = client.bars(["AAPL"], "2020-08-26", "2020-09-02", adjustment="raw", feed=feed)["AAPL"]
        adj = client.bars(["AAPL"], "2020-08-26", "2020-09-02", adjustment="split", feed=feed)["AAPL"]
        if raw and adj:
            line(abs(float(raw[0]["c"]) / float(adj[0]["c"]) - 4) < 0.5, f"split adjustment works: AAPL 2020-08-26 raw {raw[0]['c']} vs split-adjusted {adj[0]['c']}")
        ca = client.corporate_actions(["AAPL", "QQQ", "SPY"], "2024-01-01", config.today().isoformat())
        counts = {s: len(v) for s, v in ca["dividends"].items()}
        line(any(counts.values()), f"dividend history available: {counts}")
        if args.verify_dividends:
            for sym in ("AAPL", "SPY"):
                res = service.verify_dividends(client, sym, "2023-01-01", (config.today() - timedelta(days=5)).isoformat(), feed)
                bad = [r for r in res if not r["ok"]]
                line(bool(res) and not bad, f"{sym}: {len(res)} dividends cross-checked against Alpaca's dividend-adjusted bars; {len(bad)} mismatched")
                for r in bad[:3]:
                    print("        mismatch", r)
    except AlpacaError as e:
        line(False, str(e))
    print("\nAll checks passed." if ok else "\nSome checks failed; see above.")
    return 0 if ok else 1


def cmd_sync(args) -> int:
    symbols = [s.upper() for s in args.symbols] or config.load_universe()
    symbols = list(dict.fromkeys([config.BENCHMARK] + symbols))
    bad = [s for s in symbols if not service.SYMBOL.match(s)]
    if bad:
        print("Invalid symbols:", ", ".join(bad), file=sys.stderr)
        return 2
    try:
        result = service.full_sync(_client(), symbols, config.data_dir(), log=lambda m: print("  " + m), years=args.years)
    except (AlpacaError, credentials.CredentialError) as e:
        print("Sync failed:", e, file=sys.stderr)
        return 1
    print(f"Wrote {len(result['written'])} series ({result['feed'].upper()} feed), {result['assets']} searchable assets, data through {result['as_of']}.")
    for sym, why in result["skipped"].items():
        print(f"  skipped {sym}: {why}")
    print(f"Private data is in {config.data_dir()} (outside the repository).")
    return 0


def cmd_serve(args) -> int:
    data = config.data_dir()
    cache = {}

    def client_factory():
        if "c" not in cache:
            try:
                cache["c"] = _client()
            except credentials.CredentialError:
                cache["c"] = None
        return cache["c"]

    def feed():
        try:
            return json.loads((data / "index.json").read_text())["meta"]["feed"]
        except (OSError, ValueError, KeyError):
            return "iex"

    server = PersonalServer("127.0.0.1", args.port, config.REPO_ROOT, data, client_factory, feed)
    print(f"Personal edition: http://localhost:{args.port}/explorer.html   (Ctrl+C to stop)")
    print("Your data is served to this computer only. Do not publish, screenshot or screen-share real market data.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_status(args) -> int:
    data = config.data_dir()
    try:
        meta = json.loads((data / "index.json").read_text())["meta"]
    except (OSError, ValueError, KeyError):
        print("No private data yet. Run: python -m personal setup, doctor, sync")
        return 1
    n = len(list((data / "series").glob("*.json")))
    print(f"{n} series, feed {meta['feed'].upper()}, data through {meta['asOf']}, {meta['count']} searchable assets, location {data}")
    return 0


def cmd_forget(args) -> int:
    print("Credentials file removed." if credentials.forget() else "No stored credentials file.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m personal", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    d = sub.add_parser("doctor")
    d.add_argument("--verify-dividends", action="store_true", help="cross-check dividend amounts against Alpaca's dividend-adjusted bars")
    d.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("sync")
    s.add_argument("symbols", nargs="*")
    s.add_argument("--years", type=int, default=config.HISTORY_YEARS)
    s.set_defaults(fn=cmd_sync)
    v = sub.add_parser("serve")
    v.add_argument("--port", type=int, default=8765)
    v.set_defaults(fn=cmd_serve)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("forget").set_defaults(fn=cmd_forget)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
