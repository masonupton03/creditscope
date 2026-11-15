"""A SIMULATED demonstration set in the SEC "company facts" format, for four FICTIONAL companies.

It exists so the Fundamentals page works before any live SEC data is built, and so the real reducer is exercised end to end.
Nothing here is SEC data and no real company is described; the files are marked "synthetic" and the page says so. Filing
references are fake and deliberately not linkable. Deterministic: the same call always writes the same files.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from . import reduce as R

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "explorer" / "sec-sample"
GENERATED = "2026-11-14T00:00:00Z"
YEARS = list(range(2015, 2025))

COMPANIES = [
    # ticker, name, cik, seed, revenue0, growth, op margin, net margin, special
    ("DEMA", "Demo Robotics Inc.", 9000001, 11, 2.4e9, 0.11, 0.17, 0.12, "restate"),
    ("DEMB", "Demo Foods Corporation", 9000002, 12, 8.1e9, 0.03, 0.09, 0.06, "tagswitch"),
    ("DEMC", "Demo Software Ltd.", 9000003, 13, 1.1e9, 0.18, 0.24, 0.20, "negequity"),
    ("DEMD", "Demo Energy Holdings", 9000004, 14, 5.5e9, 0.02, 0.05, 0.03, "week53"),
]


def fy_end(special: str, year: int) -> str:
    if special == "week53":
        return ["2016-01-02", "2017-01-07", "2018-01-06", "2019-01-05", "2020-01-04", "2021-01-02", "2022-01-01", "2023-01-07", "2024-01-06", "2025-01-04"][year - 2015]
    return f"{year}-12-31"


def accession(cik: int, year: int, n: int = 1) -> str:
    return f"{cik:010d}-{(year + 1) % 100:02d}-{n:06d}"


def make_company_facts(ticker, name, cik, seed, rev0, growth, opm, npm, special) -> dict:
    rng = random.Random(seed)
    rev = {}
    r = rev0
    for y in YEARS:
        r *= 1 + growth + rng.uniform(-0.04, 0.05) - (0.12 if (special == "week53" and y == 2020) else 0)
        rev[y] = r
    vals = {}
    for y in YEARS:
        loss = special == "week53" and y == 2020
        om = -0.04 if loss else opm + rng.uniform(-0.015, 0.015)
        nm = -0.06 if loss else npm + rng.uniform(-0.012, 0.012)
        gm = 0.35 + rng.uniform(-0.03, 0.03)
        eq0 = rev[y] * 0.55
        v = {
            "revenue": rev[y], "grossProfit": rev[y] * gm, "costOfRevenue": rev[y] * (1 - gm), "operatingIncome": rev[y] * om,
            "netIncome": rev[y] * nm, "epsDiluted": rev[y] * nm / 480e6 * 1.0, "operatingCashFlow": rev[y] * (nm + 0.06 + rng.uniform(-0.01, 0.02)),
            "capex": rev[y] * (0.045 + rng.uniform(-0.01, 0.01)), "assets": rev[y] * 1.35, "liabilities": rev[y] * 0.8, "equity": eq0,
            "cash": rev[y] * (0.12 + rng.uniform(-0.03, 0.03)), "ltd": rev[y] * 0.22, "debtCurrent": rev[y] * 0.03,
        }
        if special == "negequity" and y >= 2020:
            v["equity"] = -rev[y] * 0.1
            v["liabilities"] = v["assets"] - v["equity"]
        vals[y] = v

    def rev_tag(y):
        return "SalesRevenueNet" if special == "tagswitch" and y <= 2017 else "RevenueFromContractWithCustomerExcludingAssessedTax" if special == "tagswitch" else "Revenues"

    facts = {}

    def add(tag, unit, fact):
        facts.setdefault(tag, {"units": {}})["units"].setdefault(unit, []).append(fact)

    def duration(tag, y, value, filing_year, unit="USD", form="10-K", n=1):
        end = fy_end(special, y)
        start = (date.fromisoformat(fy_end(special, y - 1) if y > 2015 else f"{y - 1}-12-31") + timedelta(days=1)).isoformat() if special == "week53" or y > 2015 else f"{y}-01-01"
        add(tag, unit, {"start": start, "end": end, "val": round(value, 2 if unit != "USD/shares" else 2), "accn": accession(cik, filing_year - 1, n),
                        "fy": filing_year - 1, "fp": "FY", "form": form, "filed": f"{filing_year}-02-{10 + (cik % 9):02d}"})

    def instant(tag, y, value, filing_year, n=1):
        add(tag, "USD", {"end": fy_end(special, y), "val": round(value, 2), "accn": accession(cik, filing_year - 1, n), "fy": filing_year - 1, "fp": "FY",
                         "form": "10-K", "filed": f"{filing_year}-02-{10 + (cik % 9):02d}"})

    for y in YEARS:
        for filing in (y + 1, y + 2):                                  # the original 10-K and the next year's comparative
            if filing > YEARS[-1] + 1:
                continue
            restated = special == "restate" and y == 2019 and filing == 2021
            mult = 1.03 if restated else 1.0                             # a restated comparative: the LATER filing must win
            for key, tag in (("revenue", rev_tag(y)), ("grossProfit", "GrossProfit"), ("costOfRevenue", "CostOfRevenue"), ("operatingIncome", "OperatingIncomeLoss"),
                             ("netIncome", "NetIncomeLoss"), ("operatingCashFlow", "NetCashProvidedByUsedInOperatingActivities")):
                duration(tag, y, vals[y][key] * (mult if key == "revenue" else 1), filing, n=1)
            duration("EarningsPerShareDiluted", y, vals[y]["epsDiluted"], filing, unit="USD/shares")
            if special != "negequity":                                   # DEMC reports no capex: a missing metric
                duration("PaymentsToAcquirePropertyPlantAndEquipment", y, vals[y]["capex"], filing)
            for key, tag in (("assets", "Assets"), ("liabilities", "Liabilities"), ("equity", "StockholdersEquity"), ("cash", "CashAndCashEquivalentsAtCarryingValue")):
                instant(tag, y, vals[y][key], filing)
            if special == "negequity":
                instant("LongTermDebt", y, vals[y]["ltd"] + vals[y]["debtCurrent"], filing)
            else:
                instant("LongTermDebtNoncurrent", y, vals[y]["ltd"], filing)
                instant("DebtCurrent", y, vals[y]["debtCurrent"], filing)
        # a quarterly fact that must be ignored (10-Q, 91 days)
        end = fy_end(special, y)
        q_end = (date.fromisoformat(end) - timedelta(days=90)).isoformat()
        add(rev_tag(y), "USD", {"start": (date.fromisoformat(q_end) - timedelta(days=91)).isoformat(), "end": q_end, "val": round(vals[y]["revenue"] / 4, 2),
                                "accn": accession(cik, y, 9), "fy": y, "fp": "Q3", "form": "10-Q", "filed": f"{y}-11-05"})
    return {"cik": cik, "entityName": name, "facts": {"us-gaap": facts}}


def write(out: Path = OUT) -> str:
    from .__main__ import build_index, write_json
    companies = []
    for spec in COMPANIES:
        ticker, name, cik = spec[0], spec[1], spec[2]
        c = R.reduce_company(make_company_facts(*spec), ticker, GENERATED, True, name)
        write_json(out / "company" / f"{ticker}.json", c)
        companies.append(c)
    write_json(out / "index.json", build_index(companies, True, GENERATED))
    return f"wrote {len(companies)} simulated companies to {out}"


if __name__ == "__main__":
    print(write())
