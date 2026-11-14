"""Reading and writing the compressed raw files in data/raw/<date>/."""
from __future__ import annotations

import gzip
import os
import re
from pathlib import Path

from .config import RAW_DIR

RAW_NAME = re.compile(r"^(?P<source>.+)\.(?P<fmt>[a-z]+)\.gz$")
DATE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def save_raw(root: Path, date: str, source: str, fmt: str, body: bytes) -> Path:
    """Write body gzip-compressed (deterministic bytes), replacing any earlier file."""
    folder = Path(root) / RAW_DIR / date
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source}.{fmt}.gz"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
            gz.write(body)
    os.replace(tmp, path)
    return path


def raw_dates(root: Path) -> list:
    base = Path(root) / RAW_DIR
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir()
                  if d.is_dir() and DATE_NAME.match(d.name) and any(d.glob("*.gz")))


def raw_files(root: Path, date: str) -> list:
    """Return [(source, fmt, path)] sorted by source name for one date."""
    out = []
    for path in sorted((Path(root) / RAW_DIR / date).glob("*.gz")):
        m = RAW_NAME.match(path.name)
        if m:
            out.append((m.group("source"), m.group("fmt"), path))
    return out


def read_raw(path: Path) -> bytes:
    with gzip.open(path, "rb") as fh:
        return fh.read()
