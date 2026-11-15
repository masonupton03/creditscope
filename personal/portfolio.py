"""Private storage for the portfolio ledger (~/.creditscope/portfolio.json, never inside the repository).

The file is read and written only through the local personal server. Writes are validated, atomic, kept owner-only (0600)
and protected by an optimistic revision so two browser tabs cannot silently overwrite each other. One backup of the
previous version is kept beside the file. The validation rules mirror assets/js/portfolio.js.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

from . import config

MAX_BYTES = 1_000_000
MAX_TX = 5000
TYPES = ("deposit", "withdrawal", "buy", "sell", "dividend", "fee")
ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,40}$")
EMPTY = {"version": 1, "baseCurrency": "USD", "benchmark": "SPY", "transactions": []}


class Conflict(Exception):
    """The file changed since the caller read it."""


class Invalid(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


def path() -> Path:
    return config.home() / "portfolio.json"


def revision_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _real_date(s) -> bool:
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def validate(p) -> list:
    """List of human-readable problems; empty means valid."""
    if not isinstance(p, dict) or not isinstance(p.get("transactions"), list):
        return ["portfolio must be an object with a transactions list"]
    errs = []
    if p.get("version") != 1:
        errs.append("version must be 1")
    if len(p["transactions"]) > MAX_TX:
        errs.append(f"more than {MAX_TX} transactions")
        return errs
    bench = p.get("benchmark", "SPY")
    if not isinstance(bench, str) or not re.fullmatch(config.SYMBOL_RE, bench):
        errs.append("benchmark must be a ticker symbol")
    seen = set()
    for i, t in enumerate(p["transactions"]):
        where = f"transaction {i + 1}"
        if not isinstance(t, dict):
            errs.append(f"{where}: not an object")
            continue
        if not _real_date(t.get("date")):
            errs.append(f"{where}: date must be a real YYYY-MM-DD date")
        kind = t.get("type")
        if kind not in TYPES:
            errs.append(f"{where}: type must be one of {', '.join(TYPES)}")
            continue
        if "id" in t:
            if not isinstance(t["id"], str) or not ID_RE.match(t["id"]) or t["id"] in seen:
                errs.append(f"{where}: id must be unique and use letters, digits, dot, dash or underscore")
            seen.add(t.get("id"))
        if kind in ("buy", "sell", "dividend") and not (isinstance(t.get("symbol"), str) and re.fullmatch(config.SYMBOL_RE, t["symbol"])):
            errs.append(f"{where}: symbol must look like AAPL or BRK.B")
        if kind in ("buy", "sell"):
            if not _num(t.get("shares")) or t["shares"] <= 0:
                errs.append(f"{where}: shares must be positive")
            if not _num(t.get("price")) or t["price"] <= 0:
                errs.append(f"{where}: price must be positive")
            if t.get("fee") is not None and (not _num(t["fee"]) or t["fee"] < 0):
                errs.append(f"{where}: fee must be zero or positive")
            for flag in ("external", "reinvest"):
                if flag in t and not isinstance(t[flag], bool):
                    errs.append(f"{where}: {flag} must be true or false")
        elif not _num(t.get("amount")) or t["amount"] <= 0:
            errs.append(f"{where}: amount must be positive")
        if "group" in t and (not isinstance(t["group"], str) or not ID_RE.match(t["group"])):
            errs.append(f"{where}: group must use letters, digits, dot, dash or underscore")
        if "note" in t and (not isinstance(t["note"], str) or len(t["note"]) > 200):
            errs.append(f"{where}: note must be text of at most 200 characters")
    return errs


def load(file: Optional[Path] = None) -> tuple:
    """(portfolio, revision). A missing file gives an empty portfolio with revision 'new'."""
    file = file or path()
    try:
        raw = file.read_bytes()
    except FileNotFoundError:
        return dict(EMPTY, transactions=[]), "new"
    if len(raw) > MAX_BYTES:
        raise Invalid(["portfolio file is larger than 1 MB"])
    try:
        obj = json.loads(raw)
    except ValueError:
        raise Invalid(["portfolio file is not valid JSON (a backup may exist next to it)"])
    return obj, revision_of(raw)


def save(obj, base_revision: str, file: Optional[Path] = None) -> str:
    """Validate and write atomically; raises Invalid or Conflict. Returns the new revision."""
    file = file or path()
    errs = validate(obj)
    if errs:
        raise Invalid(errs)
    if config.inside_git_repo(file.parent):
        raise Invalid(["refusing to store a portfolio inside a git repository"])
    current = file.read_bytes() if file.exists() else None
    current_rev = revision_of(current) if current is not None else "new"
    if base_revision != current_rev:
        raise Conflict("the portfolio changed since you loaded it; reload and try again")
    body = (json.dumps(obj, indent=1, sort_keys=True) + "\n").encode()
    if len(body) > MAX_BYTES:
        raise Invalid(["portfolio would be larger than 1 MB"])
    file.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(file.parent, 0o700)
    except OSError:
        pass
    if current is not None:
        bak = file.with_name(file.name + ".bak")
        bak.write_bytes(current)
        os.chmod(bak, 0o600)
    tmp = file.with_name(file.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(body)
    os.replace(tmp, file)
    return revision_of(body)
