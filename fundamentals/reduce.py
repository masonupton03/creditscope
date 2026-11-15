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

from datetime import date, datetime, timezone

from . import concepts as C


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


def quality_checks(metrics: dict) -> list:
    """Flags for a human to look at. Nothing here changes or removes a value."""
    by = {k: {p["fy"]: p for p in m["points"]} for k, m in metrics.items()}
    out = []

    def add(code, fy, msg):
        out.append({"code": code, "fy": fy, "message": msg})

    for fy in sorted({y for d in by.values() for y in d}):
        v = lambda k: by.get(k, {}).get(fy, {}).get("val")
        a, l, e = v("assets"), v("liabilities"), v("equity")
        if a and l is not None and e is not None and abs(a - (l + e)) / abs(a) > C.IDENTITY_TOLERANCE:
            add("BALANCE_IDENTITY", fy, f"FY{fy}: total assets differ from liabilities plus equity by {abs(a - (l + e)) / abs(a):.1%} (minority interest or redeemable equity can explain this).")
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
    return out


def coverage(metrics: dict) -> dict:
    """What was found, which tags supplied it, and what is missing: the honest record of non-standard filers."""
    wanted = list(C.METRICS) + ["debt"]
    return {"found": {k: {"years": len(m["points"]), "tags": sorted({p["tag"] for p in m["points"]})} for k, m in metrics.items()},
            "missing": [k for k in wanted if k not in metrics]}


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
    # a metric must not carry two points for one fiscal-year label (e.g. a transition period): keep the later period end
    for m in metrics.values():
        by_fy = {}
        for p in m["points"]:
            by_fy[p["fy"]] = p
        m["points"] = [by_fy[k] for k in sorted(by_fy)]
    filed = [p["filed"] for m in metrics.values() for p in m["points"] if p.get("filed")]
    ends = [p["end"] for m in metrics.values() for p in m["points"]]
    cik = int(company.get("cik", 0))
    return {
        "ticker": ticker, "name": name or company.get("entityName") or ticker, "cik": cik, "synthetic": synthetic,
        "source": "SEC EDGAR XBRL company facts (us-gaap, annual reports)", "currency": "USD",
        "generated": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latestFiled": max(filed) if filed else None, "latestPeriodEnd": max(ends) if ends else None, "metrics": metrics,
        "coverage": coverage(metrics), "checks": quality_checks(metrics),
    }
