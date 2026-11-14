"""Write data/status.json and the per-day run log."""
from __future__ import annotations

import json
from pathlib import Path

from .config import RUNS_DIR, STATUS_FILE
from .raw import raw_dates


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False)
        fh.write("\n")


def write_run_log(root: Path, record: dict) -> Path:
    """data/runs/<date>.json holds the result of every source for that day's latest run."""
    path = Path(root) / RUNS_DIR / f"{record['date']}.json"
    write_json(path, record)
    return path


def read_run_log(root: Path, date: str):
    path = Path(root) / RUNS_DIR / f"{date}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_status(root: Path, record: dict, rows: list) -> dict:
    """The status of the latest run, as required by the assignment."""
    dates = raw_dates(root)
    run_date = record["date"]
    prev_dates = sorted({r["date"] for r in rows if r["date"] < run_date})
    prev = prev_dates[-1] if prev_dates else None
    now_ids = {r["item_id"] for r in rows if r["date"] == run_date}
    prev_ids = {r["item_id"] for r in rows if prev and r["date"] == prev}
    failed = {s["name"].split("-", 1)[-1] for s in record["sources"] if not s["ok"]}
    return {
        "run_time": record["run_time"],
        "first_run_date": dates[0] if dates else None,
        "days_with_success": len(dates),
        "items": len(now_ids),
        "new_today": sorted(now_ids - prev_ids) if prev else [],
        # an item whose download failed has not disappeared, it is reported under sources
        "gone_today": sorted(prev_ids - now_ids - failed) if prev else [],
        "sources": [{"name": s["name"], "ok": s["ok"], "count": s["count"]}
                    for s in record["sources"]],
    }


def write_status(root: Path, status: dict) -> Path:
    path = Path(root) / STATUS_FILE
    write_json(path, status)
    return path
