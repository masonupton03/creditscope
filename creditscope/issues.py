"""The daily GitHub Issue (created or updated through the gh CLI)."""
from __future__ import annotations

import json
import re
import subprocess

from .config import TOP_N_MOVERS

LABEL = "daily-update"
TITLE_PREFIX = "CreditScope daily update: "
TITLE_RE = re.compile(r"^" + re.escape(TITLE_PREFIX) + r"(\d{4}-\d{2}-\d{2})$")


def issue_title(date: str) -> str:
    return f"{TITLE_PREFIX}{date}"


def _fmt_int(text) -> str:
    try:
        return f"{int(float(text)):,}"
    except (TypeError, ValueError):
        return "n/a"


def render_body(report: dict, status: dict) -> str:
    """Markdown body for the issue. Pure function of the report and the status."""
    date = report["date"]
    lines = [f"## CreditScope: {date} (UTC)", ""]
    failed = [s for s in status["sources"] if not s["ok"]]
    ok_count = len(status["sources"]) - len(failed)
    lines.append(f"Run time: {status['run_time']} | Sources OK: {ok_count}/{len(status['sources'])}"
                 f" | Items: {status['items']} | Days collected: {status['days_with_success']}")
    lines.append("")
    if failed:
        lines.append("**Failed sources (no raw file written for these today):** "
                     + ", ".join(f"`{s['name']}`" for s in failed))
        lines.append("")
    if report["items"] == 0:
        lines += ["No data was collected in this run (every source failed), so there is nothing to compare.", ""]
    elif not report["prev_date"]:
        lines += [f"First run: baseline recorded for {report['items']} items. "
                  "Moves will appear from the next run.", ""]
    else:
        pd, ppd = report.get("latest_price_date") or "unknown", report.get("prev_price_date") or "unknown"
        if report["new_session"]:
            lines.append(f"New market data: quotes are from the {pd} trading session "
                         f"(previous run: {ppd}).")
        else:
            lines.append(f"No new trading session since the previous run: the source still reports "
                         f"{pd} prices. Unchanged values are carried-over quotes, not new market activity.")
        lines.append("")
        if report["movers"]:
            lines += [f"### Biggest moves since {report['prev_date']} (top {TOP_N_MOVERS} by absolute % change in price)", "",
                      "| ETF | Old price | New price | Move | Old volume | New volume |",
                      "|---|---:|---:|---:|---:|---:|"]
            for m in report["movers"]:
                lines.append(f"| {m['item_id']} | ${m['old_price']} | ${m['new_price']} | "
                             f"{m['pct']:+.2f}% | {_fmt_int(m['old_volume'])} | {_fmt_int(m['new_volume'])} |")
            lines.append("")
        else:
            lines += ["No item changed price since the previous run.", ""]
    if report["new_items"]:
        lines += ["**Appeared:** " + ", ".join(report["new_items"]), ""]
    if report["gone_items"]:
        lines += ["**Disappeared:** " + ", ".join(report["gone_items"]), ""]
    lines += ["---",
              "Move rule: percent change in `price` versus the previous run, ranked by absolute value. "
              "Prices are in USD; volume is shares traded."]
    return "\n".join(lines) + "\n"


def gh(*args, stdin=None) -> str:
    proc = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {proc.stderr.strip()}")
    return proc.stdout


def publish(report: dict, status: dict) -> dict:
    """Create today's issue (or update it on a rerun) and close earlier daily issues."""
    date = report["date"]
    title, body = issue_title(date), render_body(report, status)
    gh("label", "create", LABEL, "--force", "--color", "0b5fff",
       "--description", "Automated daily CreditScope report")
    existing = json.loads(gh("issue", "list", "--label", LABEL, "--state", "all",
                             "--limit", "300", "--json", "number,title,state"))
    today = next((i for i in existing if i["title"] == title), None)
    if today:
        gh("issue", "edit", str(today["number"]), "--body-file", "-", stdin=body)
        if today["state"] != "OPEN":
            gh("issue", "reopen", str(today["number"]))
        number, action = today["number"], "updated"
    else:
        url = gh("issue", "create", "--title", title, "--label", LABEL, "--body-file", "-", stdin=body).strip()
        number, action = int(url.rstrip("/").rsplit("/", 1)[-1]), "created"
    closed = []
    for issue in existing:
        m = TITLE_RE.match(issue["title"])
        if m and issue["state"] == "OPEN" and m.group(1) < date:
            gh("issue", "close", str(issue["number"]), "--comment", f"Superseded by #{number} ({date}).")
            closed.append(issue["number"])
    return {"number": number, "action": action, "closed": closed}
