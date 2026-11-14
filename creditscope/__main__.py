"""Command line: python -m creditscope run | build | issue"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .build import build
from .config import ROOT, STATUS_FILE
from .moves import compare_runs
from .run import run_pipeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="creditscope")
    parser.add_argument("command", choices=["run", "build", "issue"],
                        help="run = download + build + status; build = rebuild history.csv from "
                             "data/raw only; issue = create/update today's GitHub Issue")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if args.command == "build":
        rows = build(args.root)
        print(f"history.csv rebuilt: {len(rows)} rows from data/raw")
        return 0
    if args.command == "run":
        status = run_pipeline(args.root)
        ok = sum(1 for s in status["sources"] if s["ok"])
        print(f"run {status['run_time']}: {ok}/{len(status['sources'])} sources ok, "
              f"{status['items']} items, {status['days_with_success']} day(s) collected")
        return 0
    if args.command == "issue":
        from .issues import publish
        from .moves import load_history
        status = json.loads((args.root / STATUS_FILE).read_text(encoding="utf-8"))
        failed = [x["name"].split("-", 1)[-1] for x in status["sources"] if not x["ok"]]
        report = compare_runs(load_history(args.root), failed_ids=failed)
        run_date = status["run_time"][:10]
        if report["date"] != run_date:
            # every source failed today: nothing new in the history, but the issue is still opened
            report = {"date": run_date, "prev_date": report["date"], "movers": [], "new_items": [],
                      "gone_items": [], "items": 0, "new_session": False, "unchanged": 0}
        result = publish(report, status)
        print(f"issue #{result['number']} {result['action']}; closed earlier: {result['closed']}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
