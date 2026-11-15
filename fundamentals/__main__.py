"""python -m fundamentals build [--tickers AAPL,MSFT] [--out explorer/sec] [--universe FILE]

Writes explorer/sec/index.json and explorer/sec/company/<TICKER>.json from live SEC data. Requires SEC_USER_AGENT.
`python -m fundamentals sample` rebuilds the SIMULATED demo set in explorer/sec-sample (no network, no SEC data).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import reduce as R
from .sec import SecClient, SecError, user_agent_from_env

ROOT = Path(__file__).resolve().parent.parent
UNIVERSE = Path(__file__).resolve().parent / "universe.txt"
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def read_universe(path: Path = UNIVERSE) -> list:
    out = []
    for line in path.read_text().splitlines():
        line = line.split("#")[0].strip().upper()
        if line and SYMBOL.match(line):
            out.append(line)
    return list(dict.fromkeys(out))


def build_index(companies: list, synthetic: bool, generated: str) -> dict:
    entries = [{"s": c["ticker"], "n": c["name"], "t": "S", "x": "", "c": c["cik"], "f": c["latestFiled"], "e": c["latestPeriodEnd"]} for c in companies]
    entries.sort(key=lambda e: e["s"])
    return {"meta": {"synthetic": synthetic, "generated": generated, "count": len(entries),
                     "source": "Simulated demonstration data (not SEC data)" if synthetic else "SEC EDGAR XBRL company facts"}, "entries": entries}


def build(client, tickers: list, out: Path, log=print, raw_dir: Path = None, offline: bool = False) -> dict:
    """Fetch (or, with offline=True, re-read the copies saved in raw_dir) and reduce. raw_dir keeps the SEC responses OUTSIDE the
    repository so a rule change can be re-run, and a surprising figure explained, without contacting the SEC again."""
    if offline:
        directory = json.loads((raw_dir / "directory.json").read_text())
    else:
        directory = client.tickers()
        if raw_dir:
            write_json(raw_dir / "directory.json", {t: directory[t] for t in tickers if t in directory})
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    done, skipped = [], {}
    for t in tickers:
        info = directory.get(t)
        if not info:
            skipped[t] = "not in the SEC ticker file"
            continue
        if offline:
            rf = raw_dir / f"facts-{t}.json"
            facts = json.loads(rf.read_text()) if rf.exists() else None
        else:
            facts = client.company_facts(info["cik"])
            if facts and raw_dir:
                write_json(raw_dir / f"facts-{t}.json", facts)
        if not facts:
            skipped[t] = "no company facts published"
            continue
        c = R.reduce_company(facts, t, generated, False, info["name"])
        if not c["metrics"]:
            skipped[t] = "no annual us-gaap facts (foreign filer or no XBRL)"
            continue
        write_json(out / "company" / f"{t}.json", c)
        done.append(c)
        log(f"{t}: {len(c['metrics'])} metrics, latest period {c['latestPeriodEnd']}")
    write_json(out / "index.json", build_index(done, False, generated))
    return {"written": [c["ticker"] for c in done], "skipped": skipped}


FIRST_RUN = ("MSFT", "AAPL", "WMT", "JPM")


def run_preflight(args, env=None) -> int:
    """Offline readiness check: never opens a connection and never prints the contact value."""
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    bad = [t for t in tickers if not SYMBOL.match(t)]
    problems = []
    try:
        user_agent_from_env(env)
        contact = "set and well-formed (value not shown)"
    except SecError as e:
        contact = "NOT READY: " + str(e)
        problems.append("contact")
    if bad:
        problems.append("tickers")
    print("SEC contact (SEC_USER_AGENT): " + contact)
    print("Companies: " + (", ".join(tickers) if tickers else "none") + (("  INVALID: " + ", ".join(bad)) if bad else ""))
    print(f"A build would make {1 + len(tickers)} requests (1 ticker directory + 1 per company) at 5 per second; `verify` adds up to about 20 per company (one per distinct data tag).")
    print("No request was made." + (" Fix the items above, then run the build." if problems else " Ready: the build can run once you authorize it."))
    return 2 if problems else 0


def run_explain(args) -> int:
    """Offline: list every annual-report fact the reducer could have used for one metric, and which one it chose."""
    from . import concepts as C
    f = args.raw_dir / f"facts-{args.ticker.upper()}.json"
    if not f.exists():
        print(f"no saved response {f} (run build with --raw-dir first)", file=sys.stderr)
        return 2
    facts = json.loads(f.read_text())
    spec = C.METRICS.get(args.metric)
    tags = spec["tags"] if spec else (C.DEBT_TOTAL + C.DEBT_NONCURRENT + C.DEBT_CURRENT if args.metric == "debt" else None)
    if not tags:
        print("unknown metric; choose one of: " + ", ".join(list(C.METRICS) + ["debt"]), file=sys.stderr)
        return 2
    unit = spec["unit"] if spec else "USD"
    for tag in tags:
        rows = [r for r in R._facts(facts, tag, unit) if (not args.year or str(r.get("end", "")).startswith(str(args.year)) or str(r.get("fy")) == str(args.year))]
        print(f"-- {tag}: {len(rows)} fact(s)")
        for r in sorted(rows, key=lambda r: (r.get("end", ""), r.get("filed", "")))[-args.limit:]:
            span = (R._days(r["start"], r["end"]) if r.get("start") else None)
            print(f"   {r.get('start','')}..{r.get('end')} ({span} d) val {r.get('val')}  form {r.get('form')}  filed {r.get('filed')}  fy {r.get('fy')} {r.get('fp')}  accn {r.get('accn')}")
    return 0


def run_review(args) -> int:
    """Offline report on built company files: coverage, tag choices, data checks, derived values worth a second look."""
    files = sorted((args.out / "company").glob("*.json"))
    if not files:
        print(f"no company files in {args.out / 'company'}", file=sys.stderr)
        return 2
    for f in files:
        c = json.loads(f.read_text())
        print(f"== {c['ticker']}  {c['name']}  (CIK {c['cik']})  latest fiscal period ends {c['latestPeriodEnd']}, filed {c['latestFiled']}  [{f.stat().st_size // 1024} KB]")
        cov = c.get("coverage", {})
        print(f"  profile: {c.get('profile', 'general')}" + (f" ({c['profileReason']})" if c.get("profileReason") else ""))
        print("  not reported: " + (", ".join(cov.get("missing", [])) or "nothing"))
        for k, d in cov.get("stale", {}).items():
            print(f"  NOT SHOWN (stale): {d['label']} last reported FY{d['lastFy']} ({d['val']:,.0f}, tag {d['tag']}, filed {d['filed']}); company reports through FY{d['companyLatestFy']}")
        for k, runs in cov.get("definitions", {}).items():
            print(f"  DEFINITION CHANGES in {k}: " + "; ".join(f"FY{r['fromFy']}-FY{r['toFy']} {r['meaning']}" for r in runs))
        bs = {k: {p["fy"]: p["accn"] for p in c["metrics"][k]["points"]} for k in ("assets", "liabilities", "equity") if k in c["metrics"]}
        mixed = [fy for fy in (bs.get("assets") or {}) if len({bs[k].get(fy) for k in bs if fy in bs[k]}) > 1]
        print("  balance sheet: each year from one filing" if not mixed else f"  balance sheet: MIXED FILINGS in FY{mixed}")
        for k, v in cov.get("found", {}).items():
            pts = c["metrics"][k]["points"]
            print(f"  {k:<18} {v['years']:>2} yrs  FY{pts[0]['fy']}-FY{pts[-1]['fy']}  latest {pts[-1]['val']:,.2f} {c['metrics'][k]['unit']}  via {', '.join(v['tags'])}")
        for chk in c.get("checks", []):
            print(f"  CHECK {chk['code']}: {chk['message']}")
        if not c.get("checks"):
            print("  no data checks raised")
        by = {k: {p['fy']: p['val'] for p in m['points']} for k, m in c["metrics"].items()}
        for fy in sorted(by.get("revenue", {}))[-3:]:
            r, n = by["revenue"][fy], by.get("netIncome", {}).get(fy)
            if n is not None and r:
                print(f"  FY{fy}: revenue {r:,.0f}, net income {n:,.0f}, net margin {n / r:.1%}")
    print("\nThis report is only a map of what to look at. Figures are confirmed against the filings by hand (see `verify --sheet`).")
    return 0


def run_verify(args, ua, client=None) -> int:
    from . import verify as V
    t = args.ticker.upper()
    f = args.out / "company" / f"{t}.json"
    if not SYMBOL.match(t) or not f.exists():
        print(f"no built file for {t} in {args.out} (run the build first)", file=sys.stderr)
        return 2
    company = json.loads(f.read_text())
    try:
        res = V.cross_check(client or SecClient(ua), company, args.years)
    except SecError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.sheet:
        args.sheet.write_text(V.sheet(company, args.years))
    print(f"{t}: {res['ok']} figures re-confirmed through the concept endpoint, {len(res['mismatches'])} mismatches, {len(res['skipped'])} composite figures to check by hand.")
    for m in res["mismatches"]:
        print(f"  MISMATCH {m['metric']} FY{m['fy']} {m['tag']}: stored {m['stored']} vs {m['found']} ({m['why']})")
    return 1 if res["mismatches"] else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fundamentals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="fetch from the SEC (needs SEC_USER_AGENT)")
    b.add_argument("--raw-dir", type=Path, help="save the SEC responses here (outside the repository)")
    b.add_argument("--offline", action="store_true", help="rebuild from the responses saved in --raw-dir; makes no request")
    b.add_argument("--tickers"); b.add_argument("--universe", type=Path, default=UNIVERSE); b.add_argument("--out", type=Path, default=ROOT / "explorer" / "sec")
    sub.add_parser("sample", help="rebuild the simulated demo set (no network)")
    v = sub.add_parser("verify", help="cross-check a built company through another SEC endpoint and write a manual checklist (needs SEC_USER_AGENT)")
    v.add_argument("ticker"); v.add_argument("--out", type=Path, default=ROOT / "explorer" / "sec"); v.add_argument("--years", type=int, default=3); v.add_argument("--sheet", type=Path)
    rv = sub.add_parser("review", help="offline report on built company files (no network)")
    rv.add_argument("--out", type=Path, default=ROOT / "explorer" / "sec")
    ex = sub.add_parser("explain", help="offline: show the SEC facts behind one figure (needs build --raw-dir)")
    ex.add_argument("ticker"); ex.add_argument("metric"); ex.add_argument("--raw-dir", type=Path, required=True); ex.add_argument("--year", type=int); ex.add_argument("--limit", type=int, default=12)
    pf = sub.add_parser("preflight", help="check the contact setting and the plan WITHOUT contacting the SEC")
    pf.add_argument("--tickers", default=",".join(FIRST_RUN))
    args = ap.parse_args(argv)
    if args.cmd == "preflight":
        return run_preflight(args)
    if args.cmd == "review":
        return run_review(args)
    if args.cmd == "explain":
        return run_explain(args)
    if args.cmd == "build" and args.offline:
        if not args.raw_dir:
            print("--offline needs --raw-dir", file=sys.stderr)
            return 2
        tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else read_universe(args.universe)
        res = build(None, tickers, args.out, raw_dir=args.raw_dir, offline=True)
        print(f"Rebuilt {len(res['written'])} companies from saved responses (no request made); skipped {len(res['skipped'])}.")
        return 0
    if args.cmd == "sample":
        from . import sample
        print(sample.write())
        return 0
    try:
        ua = user_agent_from_env()
    except SecError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.cmd == "verify":
        return run_verify(args, ua)
    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else read_universe(args.universe)
    bad = [t for t in tickers if not SYMBOL.match(t)]
    if bad:
        print("invalid ticker(s): " + ", ".join(bad), file=sys.stderr)
        return 2
    try:
        res = build(SecClient(ua), tickers, args.out, raw_dir=args.raw_dir)
    except SecError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Wrote {len(res['written'])} companies to {args.out}; skipped {len(res['skipped'])}.")
    for t, why in res["skipped"].items():
        print(f"  {t}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
