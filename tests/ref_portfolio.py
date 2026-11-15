"""Independent Python implementation of the portfolio analytics (test reference only).

Follows docs/portfolio-dashboard.md but is written differently from assets/js/portfolio.js: transactions are grouped per
trading day in dictionaries, returns are linked through logarithms, prices come from bisect, and the lots are consumed with a
deque. Agreement between the two is evidence that the browser computes what the specification says.
"""
from __future__ import annotations

import bisect
import math
import statistics
from collections import defaultdict, deque

import ref_finance as rf

RANK = {"deposit": 0, "buy": 1, "dividend": 2, "sell": 3, "withdrawal": 4, "fee": 5}
PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "ITD"]
TOL = 1e-9


class Oversell(Exception):
    pass


def split_factor(series, date):
    out = 1.0
    for ex, ratio in (series.get("splits") or []):
        if ex > date:
            out *= ratio
    return out


def _run(ledger, cal, series, held, auto_div, with_div):
    """Returns per-day dicts: value, cash, flow, incomplete and the final book."""
    by_day = defaultdict(list)
    for tx in ledger:
        by_day[tx["idx"]].append(tx)
    pos = defaultdict(float)
    lots = defaultdict(deque)
    cash = realized = fees = 0.0
    div_by_symbol = defaultdict(float)
    value, cash_hist, flow, incomplete = [], [], [], []
    for i in range(len(cal)):
        day_flow = 0.0
        if with_div:
            for sym, schedule in auto_div.items():
                if i in schedule and pos[sym] > 0:
                    got = schedule[i] * pos[sym]
                    cash += got
                    div_by_symbol[sym] += got
        for tx in by_day.get(i, []):
            kind = tx["type"]
            if kind == "deposit":
                cash += tx["amount"]; day_flow += tx["amount"]
            elif kind == "withdrawal":
                cash -= tx["amount"]; day_flow -= tx["amount"]
            elif kind == "fee":
                cash -= tx["amount"]; fees += tx["amount"]
            elif kind == "dividend":
                if with_div:
                    cash += tx["amount"]; div_by_symbol[tx["symbol"]] += tx["amount"]
            elif kind == "buy":
                cost = tx["shares"] * tx["price"] + tx["fee"]
                if tx["external"]:
                    day_flow += cost
                else:
                    cash -= cost
                fees += tx["fee"]
                pos[tx["symbol"]] += tx["adj"]
                lots[tx["symbol"]].append([tx["adj"], cost])
            else:  # sell
                if tx["adj"] > pos[tx["symbol"]] * (1 + TOL) + TOL:
                    raise Oversell(tx["input"])
                proceeds = tx["shares"] * tx["price"] - tx["fee"]
                if tx["external"]:
                    day_flow -= proceeds
                else:
                    cash += proceeds
                fees += tx["fee"]
                remaining = min(tx["adj"], pos[tx["symbol"]])
                used = 0.0
                q = lots[tx["symbol"]]
                while remaining > TOL * 0.01 and q:
                    lot = q[0]
                    take = min(lot[0], remaining)
                    piece = lot[1] * take / lot[0]
                    lot[1] -= piece; lot[0] -= take; remaining -= take; used += piece
                    if lot[0] <= TOL * 0.01:
                        q.popleft()
                realized += proceeds - used
                pos[tx["symbol"]] -= min(tx["adj"], pos[tx["symbol"]])
        total, missing = cash, False
        for sym, sh in pos.items():
            if sh <= 0:
                continue
            j = bisect.bisect_right(series[sym]["dates"], cal[i]) - 1
            if j < 0:
                missing = True
            else:
                total += sh * series[sym]["close"][j]
        value.append(total); cash_hist.append(cash); flow.append(day_flow); incomplete.append(missing)
    return {"value": value, "cash": cash_hist, "flow": flow, "incomplete": incomplete, "pos": dict(pos),
            "lots": {k: [list(x) for x in v] for k, v in lots.items()}, "cash_end": cash, "realized": realized,
            "fees": fees, "div": dict(div_by_symbol)}


def analyze(portfolio, series, benchmark="SPY"):
    bench = series[benchmark]
    cal = bench["dates"]
    n = len(cal)
    ledger = []
    for k, tx in enumerate(portfolio["transactions"]):
        t = dict(tx, input=k, fee=tx.get("fee") or 0.0, external=bool(tx.get("external")))
        if t["date"] > cal[-1]:
            continue
        t["idx"] = bisect.bisect_left(cal, t["date"])
        if t["type"] in ("buy", "sell"):
            t["adj"] = t["shares"] * split_factor(series.get(t["symbol"], {}), t["date"])
        ledger.append(t)
    ledger.sort(key=lambda t: (t["date"], RANK[t["type"]], t["input"]))
    held = []
    for t in ledger:
        if t["type"] == "buy" and t["symbol"] not in held:
            held.append(t["symbol"])
    manual = {t["symbol"] for t in ledger if t["type"] == "dividend"}
    auto_div, unknown = {}, []
    for sym in held:
        if sym in manual:
            continue
        d = series[sym].get("dividends")
        if d is None:
            unknown.append(sym)
            continue
        sched = defaultdict(float)
        for ex, amount in d:
            if cal[0] < ex <= cal[-1]:
                sched[bisect.bisect_left(cal, ex)] += amount
        auto_div[sym] = dict(sched)
    basis = "total" if bench.get("dividends") is not None and not unknown else "price"
    first = ledger[0]["idx"]
    full = _run(ledger, cal, series, held, auto_div, True)
    sim = full if basis == "total" else _run(ledger, cal, series, held, auto_div, False)
    bad = [i for i in range(first, n) if full["incomplete"][i]]
    start = max(first, (bad[-1] + 1) if bad else 0)

    # time-weighted chain through log returns
    logs = {start: 0.0}
    daily = {}
    for i in range(start + 1, n):
        prev = sim["value"][i - 1]
        daily[i] = (sim["value"][i] - sim["flow"][i]) / prev - 1.0 if prev > 0 else 0.0
        logs[i] = logs[i - 1] + math.log1p(daily[i])
    level = {i: math.exp(v) for i, v in logs.items()}
    bl = rf.level_series(bench, basis)
    bench_r = {i: bl[i] / bl[i - 1] - 1.0 for i in range(1, n)}
    cum_flow = []
    run = 0.0
    for f in full["flow"]:
        run += f
        cum_flow.append(run)

    perf = {}
    last = cal[-1]
    for period in PERIODS:
        sd = cal[start] if period == "ITD" else rf.start_date(period, last, cal[start])
        a = bisect.bisect_right(cal, sd) - 1
        truncated = False
        if a < start:
            a, truncated = start, period != "ITD"
        b = n - 1
        if b <= a:
            continue
        days = (rf.to_date(cal[b]) - rf.to_date(cal[a])).days
        twr = level[b] / level[a] - 1.0
        flows = [(i, sim["flow"][i]) for i in range(a + 1, b + 1)]
        net = sum(f for _, f in flows)
        weighted = sum(f * (days - (rf.to_date(cal[i]) - rf.to_date(cal[a])).days) / days for i, f in flows)
        den = sim["value"][a] + weighted
        rets = [daily[i] for i in range(a + 1, b + 1)]
        rb = [bench_r[i] for i in range(a + 1, b + 1)]
        beta = corr = None
        if len(rets) >= 60:
            vb = rf.cov(rb, rb)
            beta = rf.cov(rets, rb) / vb if vb > 0 else None
            sa, sb = statistics.stdev(rets), statistics.stdev(rb)
            corr = rf.cov(rets, rb) / (sa * sb) if sa > 0 and sb > 0 else None
        lv = [level[i] if i in level else None for i in range(n)]
        perf[period] = {
            "startDate": cal[a], "endDate": cal[b], "days": days, "truncated": truncated, "nReturns": len(rets),
            "valueStart": full["value"][a], "valueEnd": full["value"][b], "valueChange": full["value"][b] - full["value"][a],
            "netFlows": net, "investmentGain": full["value"][b] - full["value"][a] - net,
            "twr": twr, "annualizedTwr": math.expm1(math.log1p(twr) * 365.25 / days) if days >= 365 else None,
            "modifiedDietz": (sim["value"][b] - sim["value"][a] - net) / den if den > 0 else None,
            "benchmarkReturn": bl[b] / bl[a] - 1.0, "excess": twr - (bl[b] / bl[a] - 1.0),
            "volatility": statistics.stdev(rets) * math.sqrt(252) if len(rets) >= 20 else None,
            "benchmarkVolatility": statistics.stdev(rb) * math.sqrt(252) if len(rb) >= 20 else None,
            "beta": beta, "correlation": corr, "maxDrawdown": rf.drawdown(lv, list(range(a, b + 1)), cal),
        }

    end = n - 1
    rows = {}
    for sym, sh in full["pos"].items():
        if sh <= TOL * 0.01:
            continue
        j = bisect.bisect_right(series[sym]["dates"], cal[end]) - 1
        price = series[sym]["close"][j] if j >= 0 else None
        cost = sum(c for _, c in full["lots"][sym])
        rows[sym] = {"shares": sh, "price": price, "costBasis": cost, "marketValue": sh * price,
                     "unrealized": sh * price - cost, "dividendsReceived": full["div"].get(sym, 0.0)}
    invested = sum(r["marketValue"] for r in rows.values())
    total = full["cash_end"] + invested
    weights = sorted((r["marketValue"] / invested for r in rows.values()), reverse=True) if invested > 0 else []
    hhi = sum(w * w for w in weights)
    return {
        "basis": basis, "startDate": cal[start], "perf": perf, "holdings": rows,
        "totals": {"totalValue": total, "marketValue": invested, "cash": full["cash_end"],
                   "costBasis": sum(r["costBasis"] for r in rows.values()),
                   "unrealized": sum(r["unrealized"] for r in rows.values()), "realized": full["realized"],
                   "dividends": sum(full["div"].values()), "fees": full["fees"]},
        "concentration": {"top1": sum(weights[:1]), "top3": sum(weights[:3]), "top5": sum(weights[:5]), "hhi": hhi,
                          "effectiveN": 1 / hhi if hhi > 0 else None},
        "valueSeries": full["value"][start:],
    }
