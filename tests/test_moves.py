"""The move rule and the comparison of the latest run with the previous one."""
import pytest

from creditscope.moves import compare_runs, percent_move, rank_movers


def row(date, item_id, price, price_date="2026-11-13", volume="1000", item=None):
    return {"date": date, "item_id": item_id, "item": item or item_id, "price": price,
            "volume": volume, "price_date": price_date}


def test_percent_move_values():
    assert percent_move("100", "110") == pytest.approx(10.0)
    assert percent_move("100", "90") == pytest.approx(-10.0)
    assert percent_move("100", "100") == 0.0
    assert percent_move("200.50", "201.0") == pytest.approx(0.2494, abs=1e-3)


@pytest.mark.parametrize("old,new", [("0", "5"), ("", "5"), ("5", ""), (None, "5"), ("x", "5")])
def test_percent_move_not_computable(old, new):
    assert percent_move(old, new) is None


def test_rank_by_absolute_move_with_old_and_new_values():
    prev = {"A": row("d1", "A", "100"), "B": row("d1", "B", "100"), "C": row("d1", "C", "100")}
    now = {"A": row("d2", "A", "101"), "B": row("d2", "B", "95"), "C": row("d2", "C", "100")}
    movers = rank_movers(prev, now)
    assert [m["item_id"] for m in movers] == ["B", "A"]      # C unchanged: excluded
    assert movers[0]["old_price"] == "100" and movers[0]["new_price"] == "95"
    assert movers[0]["pct"] == pytest.approx(-5.0)


def test_rank_top_n_and_tie_break_by_item_id():
    prev = {s: row("d1", s, "100") for s in "ABCDEFG"}
    now = {s: row("d2", s, "102") for s in "ABCDEFG"}
    assert [m["item_id"] for m in rank_movers(prev, now, top_n=3)] == ["A", "B", "C"]


def test_rank_ignores_items_not_in_both_and_unusable_prices():
    prev = {"A": row("d1", "A", "100"), "GONE": row("d1", "GONE", "10"), "Z": row("d1", "Z", "0")}
    now = {"A": row("d2", "A", "110"), "NEW": row("d2", "NEW", "10"), "Z": row("d2", "Z", "5")}
    assert [m["item_id"] for m in rank_movers(prev, now)] == ["A"]


def test_compare_runs_empty_and_first_run():
    assert compare_runs([])["date"] is None
    first = compare_runs([row("2026-11-14", "A", "10")])
    assert first["prev_date"] is None and first["movers"] == []
    assert first["new_items"] == [] and first["items"] == 1


def test_compare_runs_new_and_gone_items():
    rows = [row("2026-11-14", "A", "10"), row("2026-11-14", "B", "10"),
            row("2026-11-15", "A", "11"), row("2026-11-15", "C", "10")]
    rep = compare_runs(rows)
    assert (rep["date"], rep["prev_date"]) == ("2026-11-15", "2026-11-14")
    assert rep["new_items"] == ["C"] and rep["gone_items"] == ["B"]
    assert [m["item_id"] for m in rep["movers"]] == ["A"]


def test_failed_source_is_not_reported_as_gone():
    rows = [row("2026-11-14", "A", "10"), row("2026-11-14", "B", "10"), row("2026-11-15", "A", "10")]
    assert compare_runs(rows, failed_ids=["B"])["gone_items"] == []


def test_compares_against_previous_run_even_with_gap_days():
    rows = [row("2026-11-14", "A", "10"), row("2026-11-20", "A", "12")]
    rep = compare_runs(rows)
    assert rep["prev_date"] == "2026-11-14" and rep["movers"][0]["pct"] == pytest.approx(20.0)


def test_weekend_carryover_is_not_a_new_session():
    same = compare_runs([row("2026-11-14", "A", "10", "2026-11-13"), row("2026-11-15", "A", "10", "2026-11-13")])
    assert same["new_session"] is False and same["movers"] == [] and same["unchanged"] == 1
    new = compare_runs([row("2026-11-15", "A", "10", "2026-11-13"), row("2026-11-16", "A", "11", "2026-11-16")])
    assert new["new_session"] is True and len(new["movers"]) == 1
