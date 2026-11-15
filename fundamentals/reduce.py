"""Reduce one company's SEC "company facts" JSON to a compact annual table.

Rules (all covered by tests/test_fundamentals.py):
  * only us-gaap facts from annual reports (10-K family); quarterly (10-Q) facts are not used
  * flows (revenue, income, cash flow) must span 350-380 days; balances are taken at the fiscal year end
  * the same period reported more than once (restatements, comparatives in later filings) keeps the LATEST filed value
  * the first tag in the metric's priority list that has a value for a period supplies it; the tag is stored with the value
  * fiscal-year label = year of the period end, except a 52/53-week year ending in the first week of January belongs to the year before
  * units are kept exactly as filed (USD, USD/shares); nothing is converted or estimated
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from . import concepts as C


REDUCER_VERSION = 4          # bump when the reduction rules change: published files record which rules produced them


def source_digest(company: dict) -> str:
    """SHA-256 of the SEC response this file was reduced from (canonical JSON). The raw response itself is never committed."""
    return hashlib.sha256(json.dumps(company, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def fiscal_year(end: str) -> int:
    y, m, d = int(end[:4]), int(end[5:7]), int(end[8:10])
    return y - 1 if m == 1 and d <= 7 else y


def _facts(company: dict, tag: str, unit: str) -> list:
    try:
        return company["facts"]["us-gaap"][tag]["units"][unit]
    except (KeyError, TypeError):
        return []


def _annual(entries: list, kind: str) -> dict:
    """{period key: fact} for annual-report facts, keeping the latest filed per period."""
    best = {}
    for f in entries:
        if f.get("form") not in C.ANNUAL_FORMS or f.get("val") is None or not f.get("end") or not f.get("accn"):
            continue
        if kind == "duration":
            if not f.get("start") or not (C.ANNUAL_DAYS[0] <= _days(f["start"], f["end"]) <= C.ANNUAL_DAYS[1]):
                continue
            key = (f["start"], f["end"])
        else:
            key = (f["end"],)
        cur = best.get(key)
        if cur is None or (f.get("filed", ""), f["accn"]) > (cur.get("filed", ""), cur["accn"]):
            best[key] = f
    return best


def _point(f: dict, tag: str) -> dict:
    p = {"end": f["end"], "fy": fiscal_year(f["end"]), "val": f["val"], "form": f["form"], "filed": f.get("filed"), "accn": f["accn"], "tag": tag}
    if f.get("start"):
        p["start"] = f["start"]
    return p


def _metric(company: dict, spec: dict) -> list:
    chosen = {}                                                    # period end -> point
    for tag in spec["tags"]:
        for key, f in _annual(_facts(company, tag, spec["unit"]), spec["kind"]).items():
            end = key[-1]
            chosen.setdefault(end, _point(f, tag))                 # earlier tags win
    return chosen


def _balance_sheet(company: dict) -> dict:
    """{'assets'|'liabilities'|'equity': {period end: point}} with all figures of a year from ONE filing.

    For each balance sheet date, every annual filing that reports at least one of the three is a candidate. The candidate holding the most of
    them wins; ties go to the latest filing. A figure the winning filing does not contain stays unavailable: it is never taken from a
    different filing version, because that mixes restated and original numbers."""
    cand = {}                                                      # end -> accn -> key -> (priority, tag, fact)
    for key in C.BALANCE_KEYS:
        spec = C.METRICS[key]
        for prio, tag in enumerate(spec["tags"]):
            for f in _facts(company, tag, spec["unit"]):
                if f.get("form") not in C.ANNUAL_FORMS or f.get("val") is None or not f.get("end") or not f.get("accn"):
                    continue
                slot = cand.setdefault(f["end"], {}).setdefault(f["accn"], {})
                if key not in slot or prio < slot[key][0]:
                    slot[key] = (prio, tag, f)
    out = {k: {} for k in C.BALANCE_KEYS}
    for end, by_accn in cand.items():
        def rank(item):
            accn, slot = item
            filed = max(v[2].get("filed", "") for v in slot.values())
            return (len(slot), filed, accn)
        accn, slot = max(by_accn.items(), key=rank)
        for key, (_, tag, f) in slot.items():
            out[key][end] = _point(f, tag)
    return out


def _debt(company: dict) -> dict:
    total = {}
    for tag in C.DEBT_TOTAL:
        for key, f in _annual(_facts(company, tag, "USD"), "instant").items():
            total.setdefault(key[0], _point(f, tag))
    nonc = {}
    for tag in C.DEBT_NONCURRENT:
        for key, f in _annual(_facts(company, tag, "USD"), "instant").items():
            nonc.setdefault(key[0], _point(f, tag))
    cur = {}
    for tag in C.DEBT_CURRENT:
        for key, f in _annual(_facts(company, tag, "USD"), "instant").items():
            cur.setdefault(key[0], _point(f, tag))
    out = dict(total)
    for end, p in nonc.items():
        if end in out:
            continue
        q = dict(p)
        if end in cur:                                             # noncurrent + current; cite the later filing of the two
            q["val"] = p["val"] + cur[end]["val"]
            q["tag"] = p["tag"] + "+" + cur[end]["tag"]
            if (cur[end].get("filed") or "") > (p.get("filed") or ""):
                q["filed"], q["accn"], q["form"] = cur[end].get("filed"), cur[end]["accn"], cur[end]["form"]
        out[end] = q
    return out


def quality_checks(metrics: dict, stale: dict = None, definitions: dict = None) -> list:
    """Flags for a human to look at. Nothing here changes or removes a value."""
    by = {k: {p["fy"]: p for p in m["points"]} for k, m in metrics.items()}
    out = []

    def add(code, fy, msg):
        out.append({"code": code, "fy": fy, "message": msg})

    for fy in sorted({y for d in by.values() for y in d}):
        v = lambda k: by.get(k, {}).get(fy, {}).get("val")
        a, l, e = v("assets"), v("liabilities"), v("equity")
        if a and l is not None and e is not None and abs(a - (l + e)) / abs(a) > C.IDENTITY_TOLERANCE:
            filed = {k: by[k][fy].get("filed") for k in ("assets", "liabilities", "equity")}
            mixed = len(set(filed.values())) > 1
            why = ("the three figures come from different filings (" + ", ".join(f"{k} filed {d}" for k, d in filed.items()) + "), so a later restatement of only some of them is the likely cause" if mixed
                   else "minority interest or redeemable equity can explain this")
            add("BALANCE_IDENTITY", fy, f"FY{fy}: total assets differ from liabilities plus equity by {abs(a - (l + e)) / abs(a):.1%}; {why}.")
        rev, cost, gp = v("revenue"), v("costOfRevenue"), v("grossProfit")
        if rev and cost is not None and gp is not None and abs((rev - cost) - gp) / abs(rev) > C.GROSS_PROFIT_TOLERANCE:
            add("GROSS_PROFIT_MISMATCH", fy, f"FY{fy}: reported gross profit differs from revenue minus cost of revenue by {abs((rev - cost) - gp) / abs(rev):.1%} of revenue.")
        if rev is not None and rev <= 0:
            add("NONPOSITIVE_REVENUE", fy, f"FY{fy}: revenue is zero or negative.")
        prev = v("revenue") and by["revenue"].get(fy - 1)
        if prev and prev["val"] > 0 and rev and abs(rev / prev["val"] - 1) > C.JUMP_LIMIT:
            add("LARGE_REVENUE_CHANGE", fy, f"FY{fy}: revenue changed by {rev / prev['val'] - 1:+.0%}; check for an acquisition, divestiture or restatement.")
        for k, p in by.items():
            pt = p.get(fy)
            if pt and pt.get("filed") and pt["filed"] < pt["end"]:
                add("FILED_BEFORE_PERIOD_END", fy, f"FY{fy} {k}: filing date {pt['filed']} is before the period end {pt['end']}.")
    for k, d in (stale or {}).items():
        add("STALE_SERIES", d["lastFy"], f"{d['label']}: the newest value is FY{d['lastFy']} but the company reports through FY{d['companyLatestFy']}; the filer stopped using tag {d['tag']}, so the figure is not shown and nothing current is available for it.")
    for k, runs in (definitions or {}).items():
        add("DEFINITION_CHANGE", runs[0]["fromFy"], f"{metrics[k]['label']} changes meaning inside the series: " + "; ".join(f"FY{r['fromFy']}" + (f"-FY{r['toFy']}" if r["toFy"] != r["fromFy"] else "") + f" {r['meaning']}" for r in runs) + ". Years are not directly comparable across these changes.")
    last_fy = max((p["fy"] for m in metrics.values() for p in m["points"]), default=None)
    for k, m in metrics.items():
        pts = m["points"]
        if last_fy and pts[-1]["fy"] < last_fy - C.STALE_YEARS:
            add("STALE_SERIES", pts[-1]["fy"], f"{m['label']}: the newest value is FY{pts[-1]['fy']} but the company reports through FY{last_fy}; the filer stopped using tag {pts[-1]['tag']}, so nothing current is shown for it.")
        years = [p["fy"] for p in pts if not last_fy or p["fy"] >= last_fy - C.MAX_YEARS + 1]
        gaps = [y for y in range(years[0], years[-1] + 1) if y not in years] if years else []
        if gaps and pts[-1]["fy"] >= (last_fy or 0) - C.STALE_YEARS:
            add("GAP_IN_SERIES", gaps[0], f"{m['label']}: no value for " + ", ".join(f"FY{y}" for y in gaps) + " although later and earlier years exist (not reported under the tags this site reads).")
        for a, b in zip(pts, pts[1:]):
            if b["tag"] != a["tag"] and a["val"] and b["fy"] == a["fy"] + 1 and abs(b["val"] / a["val"] - 1) > C.TAG_SWITCH_JUMP and m["unit"] == "USD":
                add("TAG_SWITCH_JUMP", b["fy"], f"{m['label']}: FY{b['fy']} switches from {a['tag']} to {b['tag']} and changes by {b['val'] / a['val'] - 1:+.0%}; the definition may have changed, so compare the two years with care.")
    return out


def split_stale(metrics: dict):
    """Move a series whose newest value is long out of date out of `metrics`, so nothing can show it as current.
    Returns (metrics, stale) where stale[key] keeps the last value with its filing for the record."""
    last_fy = max((p["fy"] for m in metrics.values() for p in m["points"]), default=None)
    keep, stale = {}, {}
    for k, m in metrics.items():
        last = m["points"][-1]
        if last_fy and last["fy"] < last_fy - C.STALE_YEARS:
            stale[k] = {"label": m["label"], "lastFy": last["fy"], "tag": last["tag"], "val": last["val"], "unit": m["unit"], "filed": last.get("filed"), "accn": last["accn"], "companyLatestFy": last_fy}
        else:
            keep[k] = m
    return keep, stale


def definition_changes(metrics: dict) -> dict:
    """For metrics whose tags are not interchangeable (see concepts.MEANING): consecutive runs of the same meaning, only if there is more than one."""
    out = {}
    for k, meanings in C.MEANING.items():
        if k not in metrics:
            continue
        runs = []
        for p in metrics[k]["points"]:
            meaning = meanings.get(p["tag"], p["tag"])
            if runs and runs[-1]["meaning"] == meaning:
                runs[-1]["toFy"] = p["fy"]
            else:
                runs.append({"meaning": meaning, "tag": p["tag"], "fromFy": p["fy"], "toFy": p["fy"]})
        if len(runs) > 1:
            out[k] = runs
    return out


def profile(company: dict, metrics: dict) -> dict:
    banky = [t for t in C.BANK_FACT_TAGS if _facts(company, t, "USD")]
    if banky and "costOfRevenue" not in metrics and "operatingIncome" not in metrics:
        return {"profile": "bank", "profileReason": "reports " + ", ".join(banky) + " and has no cost of revenue or operating income"}
    return {"profile": "general", "profileReason": None}


def coverage(metrics: dict, stale: dict = None, definitions: dict = None) -> dict:
    """What was found, which tags supplied it, and what is missing: the honest record of non-standard filers."""
    wanted = list(C.METRICS) + ["debt"]
    stale = stale or {}
    return {"found": {k: {"years": len(m["points"]), "tags": sorted({p["tag"] for p in m["points"]})} for k, m in metrics.items()},
            "missing": [k for k in wanted if k not in metrics and k not in stale], "stale": stale, "definitions": definitions or {},
            "balanceSheetBasis": "Total assets, total liabilities and shareholders' equity of each fiscal year come from one filing: the latest annual filing that reports all of them. Each figure carries its own filing date and accession number."}


def reduce_company(company: dict, ticker: str, generated: str = None, synthetic: bool = False, name: str = None) -> dict:
    """The compact file the site reads. `company` is the parsed companyfacts JSON."""
    metrics = {}
    for key, spec in C.METRICS.items():
        pts = sorted(_metric(company, spec).values(), key=lambda p: p["end"])[-C.MAX_YEARS:]
        if pts:
            metrics[key] = {"label": spec["label"], "unit": spec["unit"], "kind": spec["kind"], "points": pts}
    debt = sorted(_debt(company).values(), key=lambda p: p["end"])[-C.MAX_YEARS:]
    if debt:
        metrics["debt"] = {"label": "Debt (long-term, including current portion where reported)", "unit": "USD", "kind": "instant", "points": debt}
    bs = _balance_sheet(company)
    for key in C.BALANCE_KEYS:
        pts = sorted(bs[key].values(), key=lambda p: p["end"])[-C.MAX_YEARS:]
        if pts:
            metrics[key] = {"label": C.METRICS[key]["label"], "unit": "USD", "kind": "instant", "points": pts}
        else:
            metrics.pop(key, None)
    # a metric must not carry two points for one fiscal-year label (e.g. a transition period): keep the later period end
    for m in metrics.values():
        by_fy = {}
        for p in m["points"]:
            by_fy[p["fy"]] = p
        m["points"] = [by_fy[k] for k in sorted(by_fy)]
    metrics, stale = split_stale(metrics)
    defs = definition_changes(metrics)
    prof = profile(company, metrics)
    filed = [p["filed"] for m in metrics.values() for p in m["points"] if p.get("filed")]
    ends = [p["end"] for m in metrics.values() for p in m["points"]]
    cik = int(company.get("cik", 0))
    return {
        "ticker": ticker, "name": name or company.get("entityName") or ticker, "cik": cik, "synthetic": synthetic,
        "source": "SEC EDGAR XBRL company facts (us-gaap, annual reports)", "currency": "USD",
        "generated": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latestFiled": max(filed) if filed else None, "latestPeriodEnd": max(ends) if ends else None, "metrics": metrics,
        "profile": prof["profile"], "profileReason": prof["profileReason"],
        "coverage": coverage(metrics, stale, defs), "checks": quality_checks(metrics, stale, defs),
        "reducerVersion": REDUCER_VERSION, "sourceDigest": source_digest(company),
    }
