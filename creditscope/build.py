"""Build data/history.csv from the raw files alone."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from .config import COLUMNS, HISTORY_FILE, PROVIDERS
from .convert import ConvertError, convert
from .raw import raw_dates, raw_files, read_raw


def provider_rank(provider: str) -> int:
    return PROVIDERS.index(provider) if provider in PROVIDERS else len(PROVIDERS)


def build_rows(root: Path) -> list:
    """Convert every raw file, day by day, into rows sorted by date then item_id."""
    rows = []
    for date in raw_dates(root):
        best = {}  # item_id -> (rank, source, row)
        for source, fmt, path in raw_files(root, date):
            provider = source.split("-", 1)[0]
            try:
                converted = convert(provider, date, source, read_raw(path))
            except (ConvertError, OSError, EOFError) as exc:
                print(f"warning: skipping {path}: {exc}", file=sys.stderr)
                continue
            for row in converted:
                key = (provider_rank(provider), source)
                cur = best.get(row["item_id"])
                if cur is None or key < cur[0]:
                    best[row["item_id"]] = (key, row)
        rows.extend(row for _k, row in best.values())
    rows.sort(key=lambda r: (r["date"], r["item_id"]))
    return rows


def write_history(root: Path, rows: list) -> Path:
    path = Path(root) / HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})
    return path


def build(root: Path) -> list:
    rows = build_rows(root)
    write_history(root, rows)
    return rows
