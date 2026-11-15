"""Cross-check a built company file and produce a checklist for verifying figures against the ORIGINAL filings.

Two layers (the second is manual, on purpose):
  1. automatic: every stored value is looked up again through a different SEC endpoint (companyconcept) and compared;
  2. manual: a markdown sheet lists each figure with its filing link, form, period and tag, so a person can open the filing
     and tick the number. No number is ever changed by this command.
"""
from __future__ import annotations

from . import concepts as C

TAG_UNITS = {spec_tag: spec["unit"] for spec in C.METRICS.values() for spec_tag in spec["tags"]}
TAG_UNITS.update({t: "USD" for t in C.DEBT_TOTAL + C.DEBT_NONCURRENT + C.DEBT_CURRENT})


def filing_url(cik: int, accn: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"


def cross_check(client, company: dict, years: int = 3) -> dict:
    """Re-fetch each concept and compare the latest `years` fiscal years. Returns {'ok': n, 'mismatches': [...], 'skipped': [...]}."""
    ok, bad, skipped = 0, [], []
    cache = {}
    for key, m in company["metrics"].items():
        for p in m["points"][-years:]:
            for tag in p["tag"].split("+"):
                if "+" in p["tag"]:
                    skipped.append(f"{key} FY{p['fy']}: composite of {p['tag']} (checked by hand)")
                    break
                unit = TAG_UNITS.get(tag, m["unit"])
                if tag not in cache:
                    cache[tag] = client.company_concept(company["cik"], tag)
                doc = cache[tag]
                rows = ((doc or {}).get("units") or {}).get(unit, [])
                same = [r for r in rows if r.get("end") == p["end"] and r.get("accn") == p["accn"] and (p.get("start") in (None, r.get("start")))]
                if not same:
                    bad.append({"metric": key, "fy": p["fy"], "tag": tag, "stored": p["val"], "found": None, "why": "no matching fact in the concept endpoint"})
                elif all(r["val"] != p["val"] for r in same):
                    bad.append({"metric": key, "fy": p["fy"], "tag": tag, "stored": p["val"], "found": same[0]["val"], "why": "value differs"})
                else:
                    ok += 1
    return {"ok": ok, "mismatches": bad, "skipped": skipped}


def sheet(company: dict, years: int = 3) -> str:
    """Markdown checklist for the human step: compare each number with the filing itself."""
    lines = [f"# Verification sheet: {company['ticker']} ({company['name']})", "",
             f"Built {company['generated']} from {company['source']}. Open each filing, find the figure, tick the box.", "",
             "| Done | Metric | Fiscal year | Period | Stored value | Unit | Form, filed | Tag | Filing |", "|---|---|---|---|---|---|---|---|---|"]
    for key, m in company["metrics"].items():
        for p in m["points"][-years:]:
            period = f"{p['start']} to {p['end']}" if p.get("start") else f"at {p['end']}"
            lines.append(f"| [ ] | {m['label']} | FY{p['fy']} | {period} | {p['val']:,} | {m['unit']} | {p['form']}, {p['filed']} | `{p['tag']}` | [{p['accn']}]({filing_url(company['cik'], p['accn'])}) |")
    lines += ["", "Tips: in the filing's financial statements, balances are as of the period end and flows cover the period; amounts are",
              "usually printed in millions or thousands (the stored value is in whole USD). A figure that differs because the company",
              "restated it later is expected: the stored value comes from the latest filing that reports that period."]
    if company.get("checks"):
        lines += ["", "## Automatic data checks that fired", ""] + [f"- {c['message']}" for c in company["checks"]]
    if company.get("coverage", {}).get("missing"):
        lines += ["", "## Not found under the standard tags (left blank, never estimated)", ""] + [f"- {k}" for k in company["coverage"]["missing"]]
    return "\n".join(lines) + "\n"
