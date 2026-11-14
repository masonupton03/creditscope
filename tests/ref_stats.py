"""Independent Python implementation of the Trends statistics (used only by tests).

It is deliberately written differently from assets/js/stats.js (plain csv + dict code) so that
agreement between the two is evidence that the browser computes the right numbers from history.csv.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from creditscope.moves import compare_runs


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("price", "volume", "net_change", "pct_change"):
            r[k] = float(r[k]) if r[k] != "" else None
    return rows


def mean(xs):
    return sum(xs) / len(xs)


def report(rows):
    # one observation per (item, session): the row from the latest run
    obs = {}
    for r in rows:
        sd = r["price_date"] or r["date"]
        key = (r["item_id"], sd)
        if key not in obs or r["date"] >= obs[key]["date"]:
            obs[key] = dict(r, sd=sd)
    items = sorted({i for i, _ in obs})
    sessions = sorted({sd for _, sd in obs})
    klass = {r["item_id"]: r["asset_class"] for r in rows}
    series = {i: sorted((o for (ii, _), o in obs.items() if ii == i), key=lambda o: o["sd"]) for i in items}
    runs = sorted({r["date"] for r in rows})

    returns = []
    for i in items:
        priced = [o for o in series[i] if o["price"] is not None]
        if len(priced) >= 2:
            a, b = priced[0], priced[-1]
            returns.append({"item_id": i, "first_price": a["price"], "last_price": b["price"],
                            "ret_pct": (b["price"] - a["price"]) / a["price"] * 100})
    returns.sort(key=lambda r: (-r["ret_pct"], r["item_id"]))

    last = sessions[-1]
    latest = sorted(((o["item_id"], o["pct_change"]) for (i, sd), o in obs.items()
                     if sd == last and o["pct_change"] is not None), key=lambda t: (-t[1], t[0]))

    per_session, biggest = [], None
    for sd in sessions:
        vals = [(abs(o["pct_change"]), o["item_id"], o["pct_change"]) for (i, s), o in obs.items()
                if s == sd and o["pct_change"] is not None]
        if not vals:
            continue
        top = sorted(vals, key=lambda t: (-t[0], t[1]))[0]
        per_session.append({"sd": sd, "n": len(vals), "avg_abs_pct": mean([v[0] for v in vals]),
                            "max_item": top[1], "max_pct": top[2]})
        if biggest is None or top[0] > abs(biggest["pct"]):
            biggest = {"sd": sd, "item_id": top[1], "pct": top[2]}

    class_daily = []
    for sd in sessions:
        row = {"sd": sd}
        for c in ("Stock", "Bond"):
            v = [o["pct_change"] for (i, s), o in obs.items()
                 if s == sd and klass[i] == c and o["pct_change"] is not None]
            row[c] = mean(v) if v else None
        class_daily.append(row)
    cum = {c: (mean([r["ret_pct"] for r in returns if klass[r["item_id"]] == c])
               if any(klass[r["item_id"]] == c for r in returns) else None) for c in ("Stock", "Bond")}

    volume = []
    for i in items:
        v = [o for o in series[i] if o["volume"] is not None]
        if v:
            avg = mean([o["volume"] for o in v])
            volume.append({"item_id": i, "avg_volume": avg, "latest_volume": v[-1]["volume"],
                           "ratio": v[-1]["volume"] / avg, "n": len(v)})
    total = sum(v["avg_volume"] for v in volume)
    for v in volume:
        v["share"] = v["avg_volume"] / total
    volume.sort(key=lambda v: (-v["avg_volume"], v["item_id"]))

    cmp = compare_runs([{k: ("" if r[k] is None else str(r[k])) if k in ("price", "volume") else r[k]
                         for k in ("date", "item_id", "item", "price", "volume", "price_date")} for r in rows])
    return {
        "n_rows": len(rows), "n_runs": len(runs), "n_sessions": len(sessions), "n_items": len(items),
        "first_run_date": runs[0], "last_run_date": runs[-1], "session_dates": sessions,
        "returns": returns, "latest_moves": [{"item_id": i, "pct_change": p} for i, p in latest],
        "per_session": per_session, "biggest": biggest, "class_daily": class_daily,
        "class_cumulative": cum, "volume": volume,
        "run_comparison": {"latest": cmp["date"], "prev": cmp["prev_date"],
                           "movers": [{"item_id": m["item_id"], "pct": m["pct"]} for m in cmp["movers"]],
                           "new_session": cmp["new_session"]},
    }
