"""The move rule and the comparison between the latest run and the previous run.

Move rule: for every item present in both runs, move = (price_now - price_before)
/ price_before * 100. Items are ranked by the absolute value of the move and the
top TOP_N_MOVERS with a non-zero move are listed. 'Before' is the previous date
that has rows in history.csv (the previous run).
"""
from __future__ import annotations

import csv
from pathlib import Path

from .config import HISTORY_FILE, TOP_N_MOVERS


def load_history(root: Path) -> list:
    path = Path(root) / HISTORY_FILE
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def percent_move(old, new):
    """Percent change from old to new, or None if it cannot be computed."""
    old, new = to_float(old), to_float(new)
    if old is None or new is None or old == 0:
        return None
    return (new - old) / old * 100.0


def rank_movers(prev_by_id: dict, now_by_id: dict, top_n: int = TOP_N_MOVERS) -> list:
    """Return the top_n items by absolute % move in price (ties broken by item_id)."""
    movers = []
    for item_id in sorted(set(prev_by_id) & set(now_by_id)):
        old, new = prev_by_id[item_id], now_by_id[item_id]
        pct = percent_move(old.get("price"), new.get("price"))
        if pct is None or pct == 0:
            continue
        movers.append({
            "item_id": item_id,
            "item": new.get("item", ""),
            "old_price": old.get("price", ""),
            "new_price": new.get("price", ""),
            "pct": pct,
            "old_volume": old.get("volume", ""),
            "new_volume": new.get("volume", ""),
        })
    movers.sort(key=lambda m: (-abs(m["pct"]), m["item_id"]))
    return movers[:top_n]


def compare_runs(rows: list, top_n: int = TOP_N_MOVERS, failed_ids=()) -> dict:
    """Compare the latest date in the history with the one before it.

    Items whose download failed (failed_ids) are not reported as disappeared.
    """
    dates = sorted({r["date"] for r in rows})
    if not dates:
        return {"date": None, "prev_date": None, "movers": [], "new_items": [],
                "gone_items": [], "items": 0, "new_session": False, "unchanged": 0}
    latest = dates[-1]
    prev = dates[-2] if len(dates) > 1 else None
    now_by_id = {r["item_id"]: r for r in rows if r["date"] == latest}
    prev_by_id = {r["item_id"]: r for r in rows if prev and r["date"] == prev}
    movers = rank_movers(prev_by_id, now_by_id, top_n)
    now_pd = max([r["price_date"] for r in now_by_id.values() if r["price_date"]] or [""])
    prev_pd = max([r["price_date"] for r in prev_by_id.values() if r["price_date"]] or [""])
    in_both = set(now_by_id) & set(prev_by_id)
    changed = [i for i in in_both
               if percent_move(prev_by_id[i].get("price"), now_by_id[i].get("price")) not in (None, 0)]
    return {
        "date": latest,
        "prev_date": prev,
        "movers": movers,
        "new_items": sorted(set(now_by_id) - set(prev_by_id)) if prev else [],
        "gone_items": sorted(set(prev_by_id) - set(now_by_id) - set(failed_ids)) if prev else [],
        "items": len(now_by_id),
        "new_session": bool(now_pd and prev_pd and now_pd > prev_pd),
        "latest_price_date": now_pd,
        "prev_price_date": prev_pd,
        "unchanged": len(in_both) - len(changed),
    }
