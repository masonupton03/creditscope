"""The daily issue: text for each situation, and create/update/close logic (gh is mocked)."""
import json

import pytest

from creditscope import issues
from creditscope.moves import compare_runs
from test_moves import row

STATUS = {"run_time": "2026-11-15T21:45:00Z", "first_run_date": "2026-11-14", "days_with_success": 2,
          "items": 3, "new_today": [], "gone_today": [],
          "sources": [{"name": "nasdaq-A", "ok": True, "count": 1}, {"name": "nasdaq-B", "ok": True, "count": 1}]}


def test_title_is_the_date():
    assert issues.issue_title("2026-11-15") == "CreditScope daily update: 2026-11-15"
    assert issues.TITLE_RE.match(issues.issue_title("2026-11-15")).group(1) == "2026-11-15"


def test_body_lists_movers_with_old_and_new_values():
    rows = [row("2026-11-14", "A", "100", volume="1000"), row("2026-11-15", "A", "110", "2026-11-14", "2500")]
    body = issues.render_body(compare_runs(rows), STATUS)
    assert "| A | $100 | $110 | +10.00% | 1,000 | 2,500 |" in body
    assert "New market data" in body and "Move rule" in body


def test_body_on_a_day_with_no_changes_still_renders():
    rows = [row("2026-11-14", "A", "100"), row("2026-11-15", "A", "100")]
    body = issues.render_body(compare_runs(rows), STATUS)
    assert "No item changed price" in body
    assert "No new trading session" in body and "not new market activity" in body


def test_body_first_run_appeared_disappeared_and_failures():
    first = issues.render_body(compare_runs([row("2026-11-14", "A", "1")]), STATUS)
    assert "First run" in first
    rows = [row("2026-11-14", "A", "1"), row("2026-11-14", "B", "1"), row("2026-11-15", "A", "1"), row("2026-11-15", "C", "1")]
    failed = dict(STATUS, sources=[{"name": "nasdaq-B", "ok": False, "count": 0}])
    body = issues.render_body(compare_runs(rows), failed)
    assert "**Appeared:** C" in body and "**Disappeared:** B" in body
    assert "Failed sources" in body and "`nasdaq-B`" in body


def test_body_when_every_source_failed():
    report = {"date": "2026-11-15", "prev_date": "2026-11-14", "movers": [], "new_items": [],
              "gone_items": [], "items": 0, "new_session": False, "unchanged": 0}
    assert "every source failed" in issues.render_body(report, dict(STATUS, items=0))


class FakeGh:
    def __init__(self, existing):
        self.existing, self.calls = existing, []

    def __call__(self, *args, stdin=None):
        self.calls.append((args, stdin))
        if args[:2] == ("issue", "list"):
            return json.dumps(self.existing)
        if args[:2] == ("issue", "create"):
            return "https://github.com/x/y/issues/7\n"
        return ""

    def verbs(self):
        return [" ".join(a[:2]) for a, _ in self.calls]


def report_for(date="2026-11-15"):
    return compare_runs([row("2026-11-14", "A", "1"), row(date, "A", "2")])


def test_first_issue_of_the_day_is_created_and_previous_closed(monkeypatch):
    fake = FakeGh([{"number": 3, "title": "CreditScope daily update: 2026-11-14", "state": "OPEN"},
                   {"number": 2, "title": "CreditScope daily update: 2026-11-13", "state": "CLOSED"},
                   {"number": 1, "title": "unrelated", "state": "OPEN"}])
    monkeypatch.setattr(issues, "gh", fake)
    result = issues.publish(report_for(), STATUS)
    assert result == {"number": 7, "action": "created", "closed": [3]}
    assert "issue create" in fake.verbs()
    closes = [a for a, _ in fake.calls if a[:2] == ("issue", "close")]
    assert closes == [("issue", "close", "3", "--comment", "Superseded by #7 (2026-11-15).")]


def test_rerun_updates_todays_issue_instead_of_creating_another(monkeypatch):
    fake = FakeGh([{"number": 7, "title": "CreditScope daily update: 2026-11-15", "state": "OPEN"},
                   {"number": 3, "title": "CreditScope daily update: 2026-11-14", "state": "OPEN"}])
    monkeypatch.setattr(issues, "gh", fake)
    result = issues.publish(report_for(), STATUS)
    assert result == {"number": 7, "action": "updated", "closed": [3]}
    assert "issue create" not in fake.verbs() and "issue edit" in fake.verbs()


def test_todays_issue_is_never_closed_and_future_or_closed_ones_are_left_alone(monkeypatch):
    fake = FakeGh([{"number": 7, "title": "CreditScope daily update: 2026-11-15", "state": "OPEN"},
                   {"number": 9, "title": "CreditScope daily update: 2026-11-16", "state": "OPEN"}])
    monkeypatch.setattr(issues, "gh", fake)
    assert issues.publish(report_for(), STATUS)["closed"] == []


def test_gh_failure_raises(monkeypatch):
    class P:  returncode, stderr, stdout = 1, "boom", ""
    monkeypatch.setattr(issues.subprocess, "run", lambda *a, **k: P)
    with pytest.raises(RuntimeError, match="boom"):
        issues.gh("issue", "list")
