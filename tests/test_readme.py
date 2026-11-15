"""The assignment requires the README to list every file and what it does. This keeps that true as files are added."""
import fnmatch
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ("data/raw/", "data/runs/")            # one file per source per day: described by a pattern, never listed one by one


def listed_patterns():
    pats = set()
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cur = ""
        for span in re.findall(r"`([^`\n]+)`", line):
            for part in re.split(r",\s*", span.strip()):
                part = re.sub(r"<[^>]+>", "*", part)
                if "/" in part:
                    cur = str(PurePosixPath(part).parent)
                    pats.add(part)
                elif "." in part and cur:
                    pats.add(f"{cur}/{part}")          # "`assets/js/today.js`, `browse.js`": a bare name shares the first path's folder
                elif "." in part:
                    pats.add(part)
    return pats


def test_every_tracked_file_is_listed_in_the_readme():
    pats = listed_patterns()
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    missing = [f for f in tracked if not f.startswith(GENERATED) and not any(f == p or fnmatch.fnmatch(f, p) for p in pats)]
    assert not missing, "README.md does not list: " + ", ".join(missing[:25]) + (" ..." if len(missing) > 25 else "")


def test_readme_keeps_the_assignment_sections_and_badge():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ("## How it works", "### The move rule", "## Data source", "## Columns of `data/history.csv`", "## `data/status.json`",
                    "## Rebuild the history from the raw files", "## The website", "## Tests", "## Files"):
        assert heading in text, heading
    assert "actions/workflows/tests.yml/badge.svg" in text
