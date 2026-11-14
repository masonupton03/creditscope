"""A full daily run with a fake downloader: failures, reruns, status.json, run log."""
import csv
import gzip
import json

from creditscope.build import build
from creditscope.run import run_pipeline
from conftest import at, make_fetcher, nasdaq_response

STATUS_KEYS = ["run_time", "first_run_date", "days_with_success", "items", "new_today",
               "gone_today", "sources"]


def go(root, day, **kw):
    return run_pipeline(root, now=at(day), fetcher=make_fetcher(**kw), pause=0)


def history(root):
    with open(root / "data" / "history.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def raw_names(root, day):
    return sorted(p.name for p in (root / "data" / "raw" / day).glob("*.gz"))


def test_successful_run_writes_raw_history_and_status(root):
    st = go(root, "2026-11-14")
    assert len(raw_names(root, "2026-11-14")) == 12
    assert len(history(root)) == 12
    assert list(st) == STATUS_KEYS
    assert st["run_time"] == "2026-11-14T21:45:00Z"
    assert (st["first_run_date"], st["days_with_success"], st["items"]) == ("2026-11-14", 1, 12)
    assert st["new_today"] == [] and st["gone_today"] == []
    assert all(s["ok"] and s["count"] == 1 for s in st["sources"]) and len(st["sources"]) == 12
    assert set(st["sources"][0]) == {"name", "ok", "count"}
    assert json.loads((root / "data" / "status.json").read_text()) == st


def test_failed_download_does_not_stop_the_run(root):
    st = go(root, "2026-11-14", fail={"TLT", "HYG"})
    bad = {s["name"] for s in st["sources"] if not s["ok"]}
    assert bad == {"nasdaq-TLT", "nasdaq-HYG"}
    assert "nasdaq-TLT.json.gz" not in raw_names(root, "2026-11-14")
    assert len(raw_names(root, "2026-11-14")) == 10 and st["items"] == 10
    assert all(s["count"] == 0 for s in st["sources"] if not s["ok"])


def test_failure_is_recorded_in_the_run_log(root):
    go(root, "2026-11-14", fail={"TLT"})
    log = json.loads((root / "data" / "runs" / "2026-11-14.json").read_text())
    entry = next(s for s in log["sources"] if s["name"] == "nasdaq-TLT")
    assert entry["ok"] is False and "simulated outage" in entry["error"]
    assert len(log["sources"]) == 12                     # every source, success or failure


def test_unusable_response_counts_as_failure_and_is_not_saved(root):
    st = go(root, "2026-11-14", junk={"QQQ"})
    assert not next(s for s in st["sources"] if s["name"] == "nasdaq-QQQ")["ok"]
    assert "nasdaq-QQQ.json.gz" not in raw_names(root, "2026-11-14")


def test_run_survives_every_source_failing(root):
    go(root, "2026-11-14")
    st = go(root, "2026-11-15", fail={s for s in "SPY QQQ IWM EFA EEM XLF SHY IEF TLT AGG LQD HYG".split()})
    assert st["items"] == 0 and st["days_with_success"] == 1       # no raw file, so the day does not count
    assert st["gone_today"] == []                                  # outage is not disappearance
    assert not any(s["ok"] for s in st["sources"])
    assert (root / "data" / "runs" / "2026-11-15.json").exists()


def test_all_sources_failing_on_the_first_day(root):
    st = go(root, "2026-11-14", fail={s for s in "SPY QQQ IWM EFA EEM XLF SHY IEF TLT AGG LQD HYG".split()})
    assert st["first_run_date"] is None and st["days_with_success"] == 0 and st["items"] == 0
    assert len(history(root)) == 0


def test_second_run_same_day_counts_once_and_replaces_raw(root):
    go(root, "2026-11-14", prices={"SPY": "$100.00"})
    st = run_pipeline(root, now=at("2026-11-14", 23, 30),
                      fetcher=make_fetcher(prices={"SPY": "$105.50"}), pause=0)
    rows = history(root)
    assert len(rows) == 12 and len({(r["date"], r["item_id"]) for r in rows}) == 12
    assert next(r for r in rows if r["item_id"] == "SPY")["price"] == "105.50"
    assert st["days_with_success"] == 1 and st["run_time"] == "2026-11-14T23:30:00Z"
    stored = gzip.decompress((root / "data/raw/2026-11-14/nasdaq-SPY.json.gz").read_bytes())
    assert stored == nasdaq_response("SPY", price="$105.50")
    assert len(raw_names(root, "2026-11-14")) == 12


def test_rerun_where_a_source_fails_keeps_the_earlier_raw_file(root):
    go(root, "2026-11-14", prices={"SPY": "$100.00"})
    st = go(root, "2026-11-14", fail={"SPY"}, prices={"QQQ": "$50.00"})
    assert next(r for r in history(root) if r["item_id"] == "SPY")["price"] == "100.00"
    assert not next(s for s in st["sources"] if s["name"] == "nasdaq-SPY")["ok"]
    assert next(r for r in history(root) if r["item_id"] == "QQQ")["price"] == "50.00"
    assert len(history(root)) == 12


def test_second_run_rebuilds_history_identically_to_a_fresh_build(root):
    go(root, "2026-11-14"); go(root, "2026-11-14", prices={"SPY": "$1.00"}); go(root, "2026-11-15")
    live = (root / "data" / "history.csv").read_bytes()
    build(root)
    assert (root / "data" / "history.csv").read_bytes() == live


def test_multiple_days_status_counts_and_appeared_disappeared(root):
    go(root, "2026-11-14")
    st = go(root, "2026-11-15")
    assert st["days_with_success"] == 2 and st["first_run_date"] == "2026-11-14" and st["items"] == 12
    # an item is "gone" when its raw file is absent for reasons other than a failed download
    (root / "data/raw/2026-11-15/nasdaq-LQD.json.gz").unlink()
    build(root)
    from creditscope.status import build_status
    from creditscope.status import read_run_log
    rec = read_run_log(root, "2026-11-15")
    rec["sources"] = [s for s in rec["sources"] if s["name"] != "nasdaq-LQD"]
    rows = history(root)
    st = build_status(root, rec, rows)
    assert st["gone_today"] == ["LQD"] and st["items"] == 11
    go(root, "2026-11-16")
    assert go(root, "2026-11-16")["days_with_success"] == 3


def test_utc_date_comes_from_the_moment_of_the_run(root):
    from datetime import datetime, timedelta, timezone
    late = datetime(2026, 11, 14, 23, 59, tzinfo=timezone(timedelta(hours=-5)))   # = 04:59 UTC on the 15th
    st = run_pipeline(root, now=late.astimezone(timezone.utc), fetcher=make_fetcher(), pause=0)
    assert st["first_run_date"] == "2026-11-15" and st["run_time"].endswith("04:59:00Z")
