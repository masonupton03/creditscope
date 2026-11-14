"""Building history.csv from the raw files alone."""
import csv
import gzip

from creditscope import build as build_mod
from creditscope import config
from creditscope.build import build, build_rows
from creditscope.config import COLUMNS
from creditscope.raw import save_raw
from conftest import nasdaq_response


def put(root, day, symbol, price="$100.00", **kw):
    save_raw(root, day, f"nasdaq-{symbol}", "json", nasdaq_response(symbol, price=price, **kw))


def history(root):
    build(root)
    with open(root / "data" / "history.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def test_header_starts_with_the_four_fixed_columns(root):
    put(root, "2026-11-14", "SPY")
    build(root)
    header = (root / "data" / "history.csv").read_text().splitlines()[0].split(",")
    assert header == COLUMNS and header[:4] == ["date", "item_id", "item", "source"]


def test_rows_sorted_by_date_then_item_id(root):
    for day in ("2026-11-16", "2026-11-14", "2026-11-15"):       # created out of order
        for sym in ("TLT", "AGG", "SPY"):
            put(root, day, sym)
    rows = history(root)
    keys = [(r["date"], r["item_id"]) for r in rows]
    assert keys == sorted(keys) and len(keys) == 9
    assert keys[0] == ("2026-11-14", "AGG")


def test_build_twice_gives_identical_bytes(root):
    for day in ("2026-11-14", "2026-11-15"):
        for sym in ("SPY", "QQQ"):
            put(root, day, sym, price="$123.45")
    build(root)
    first = (root / "data" / "history.csv").read_bytes()
    build(root)
    assert (root / "data" / "history.csv").read_bytes() == first


def test_history_depends_on_raw_files_only(root):
    put(root, "2026-11-14", "SPY")
    put(root, "2026-11-14", "QQQ")
    build(root)
    (root / "data" / "history.csv").write_text("tampered\n")      # stale or edited history
    (root / "data" / "status.json").write_text("{}")
    build(root)
    assert {r["item_id"] for r in history(root)} == {"SPY", "QQQ"}


def test_history_rebuilds_from_scratch_in_a_new_folder(root, tmp_path_factory):
    import shutil
    put(root, "2026-11-14", "SPY")
    put(root, "2026-11-15", "SPY", price="$101.00")
    build(root)
    other = tmp_path_factory.mktemp("clone")
    shutil.copytree(root / "data" / "raw", other / "data" / "raw")
    build(other)
    assert (other / "data" / "history.csv").read_bytes() == (root / "data" / "history.csv").read_bytes()


def test_day_without_a_raw_file_for_a_source_has_no_row_from_it(root):
    put(root, "2026-11-14", "SPY"); put(root, "2026-11-14", "QQQ")
    put(root, "2026-11-15", "SPY")                                   # QQQ failed on the 15th
    rows = history(root)
    assert [(r["date"], r["item_id"]) for r in rows] == [
        ("2026-11-14", "QQQ"), ("2026-11-14", "SPY"), ("2026-11-15", "SPY")]


def test_day_with_no_raw_files_adds_no_rows(root):
    put(root, "2026-11-14", "SPY")
    (root / "data" / "raw" / "2026-11-15").mkdir(parents=True)
    build(root)
    assert {r["date"] for r in history(root)} == {"2026-11-14"}


def test_changed_rule_applies_to_every_day(root, monkeypatch):
    for day in ("2026-11-14", "2026-11-15", "2026-11-16"):
        put(root, day, "SPY")
    build(root)
    assert {r["category"] for r in history(root)} == {"US large cap"}
    monkeypatch.setitem(config.ETF_INFO, "SPY", {"asset_class": "Stock", "category": "Benchmark"})
    build(root)
    assert {r["category"] for r in history(root)} == {"Benchmark"} and len(history(root)) == 3


def test_missing_values_are_left_empty(root):
    put(root, "2026-11-14", "SPY", volume="N/A", stamp="N/A")
    row = history(root)[0]
    assert row["volume"] == "" and row["price_date"] == "" and row["price"] == "100.00"


def test_corrupt_or_unusable_raw_files_are_skipped_not_fatal(root):
    put(root, "2026-11-14", "SPY")
    save_raw(root, "2026-11-14", "nasdaq-QQQ", "json", b"<html>blocked</html>")
    path = root / "data" / "raw" / "2026-11-14" / "nasdaq-IWM.json.gz"
    path.write_bytes(b"this is not gzip")
    assert [r["item_id"] for r in build_rows(root)] == ["SPY"]


def test_unknown_provider_files_are_ignored(root):
    put(root, "2026-11-14", "SPY")
    save_raw(root, "2026-11-14", "mystery-SPY", "json", nasdaq_response("SPY"))
    assert [r["source"] for r in build_rows(root)] == ["nasdaq-SPY"]


def test_provider_priority_when_two_sources_report_one_item(root, monkeypatch):
    monkeypatch.setattr(build_mod, "PROVIDERS", ["second", "nasdaq"])
    monkeypatch.setitem(__import__("creditscope.convert", fromlist=["x"]).CONVERTERS, "second",
                        lambda d, s, raw: [{"date": d, "item_id": "SPY", "item": "x", "source": s, "price": "1"}])
    put(root, "2026-11-14", "SPY")
    save_raw(root, "2026-11-14", "second-SPY", "json", b"{}")
    assert [r["source"] for r in build_rows(root)] == ["second-SPY"]


def test_raw_files_are_compressed_and_hold_the_original_bytes(root):
    body = nasdaq_response("SPY", price="$222.22")
    path = save_raw(root, "2026-11-14", "nasdaq-SPY", "json", body)
    assert path.name == "nasdaq-SPY.json.gz" and path.parent.name == "2026-11-14"
    assert gzip.decompress(path.read_bytes()) == body


def test_sort_does_not_depend_on_raw_file_order(root, monkeypatch):
    """File names sort 'alpha-ZZZ' before 'nasdaq-AAA', but item_id AAA must come first."""
    from creditscope import convert as convert_mod
    monkeypatch.setattr(build_mod, "PROVIDERS", ["alpha", "nasdaq"])
    monkeypatch.setitem(convert_mod.CONVERTERS, "alpha",
                        lambda d, s, raw: [{"date": d, "item_id": "ZZZ", "item": "z", "source": s, "price": "1"}])
    monkeypatch.setitem(convert_mod.CONVERTERS, "beta",
                        lambda d, s, raw: [{"date": d, "item_id": "AAA", "item": "a", "source": s, "price": "1"}])
    for day in ("2026-11-15", "2026-11-14"):
        save_raw(root, day, "alpha-ZZZ", "json", b"{}")
        save_raw(root, day, "beta-AAA", "json", b"{}")
    keys = [(r["date"], r["item_id"]) for r in build_rows(root)]
    assert keys == [("2026-11-14", "AAA"), ("2026-11-14", "ZZZ"), ("2026-11-15", "AAA"), ("2026-11-15", "ZZZ")]
