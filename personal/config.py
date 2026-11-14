"""Locations and defaults. Everything private lives under the CreditScope home directory, outside the repo."""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Symbols downloaded by `sync` when none are given: the benchmark first, then the assignment's 12 ETFs, then a few others.
DEFAULT_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "XLF", "SHY", "IEF", "TLT", "AGG", "LQD", "HYG", "VTI", "GLD"]
BENCHMARK = "SPY"
HISTORY_YEARS = 10
SYMBOL_RE = r"^[A-Z0-9][A-Z0-9.\-]{0,9}$"


def home() -> Path:
    """The private home directory (credentials, data, universe). Override with CREDITSCOPE_HOME."""
    return Path(os.environ.get("CREDITSCOPE_HOME") or (Path.home() / ".creditscope")).expanduser()


def data_dir() -> Path:
    return home() / "data"


def universe_file() -> Path:
    return home() / "universe.json"


def load_universe() -> list:
    """The user's list of symbols to keep synced (edit ~/.creditscope/universe.json), else the default."""
    try:
        raw = json.loads(universe_file().read_text())
        syms = [s.strip().upper() for s in raw if isinstance(s, str)]
        return syms or list(DEFAULT_UNIVERSE)
    except (OSError, ValueError):
        return list(DEFAULT_UNIVERSE)


def inside_git_repo(path: Path) -> bool:
    """True if path is inside any git working tree (walks up looking for .git)."""
    p = Path(path).expanduser().resolve()
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists():
            return True
    return False


def today() -> date:
    """Today's date; CREDITSCOPE_TODAY=YYYY-MM-DD overrides it (a testing aid so tests do not depend on the calendar)."""
    override = os.environ.get("CREDITSCOPE_TODAY")
    return date.fromisoformat(override) if override else date.today()
