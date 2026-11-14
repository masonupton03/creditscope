"""One daily run: download every source, save raw files, rebuild history, write status."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .build import build
from .convert import ConvertError, convert
from .raw import save_raw
from .sources import all_sources, http_get
from .status import build_status, write_run_log, write_status


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def run_pipeline(root: Path, now=None, fetcher=http_get, sources=None, pause: float = 0.5) -> dict:
    """Run the pipeline. Returns the status dict. Never raises because a source failed."""
    now = now or utc_now()
    date = now.strftime("%Y-%m-%d")
    results = []
    for src in (sources if sources is not None else all_sources()):
        try:
            body = fetcher(src.url)
            # Only a response that converts to rows is saved as the day's raw file.
            rows = convert(src.provider, date, src.name, body)
            save_raw(root, date, src.name, src.fmt, body)
            results.append({"name": src.name, "ok": True, "count": len(rows), "error": None})
        except (RuntimeError, ConvertError, OSError) as exc:
            results.append({"name": src.name, "ok": False, "count": 0, "error": str(exc)[:300]})
        if pause:
            time.sleep(pause)
    record = {"date": date, "run_time": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "sources": results}
    write_run_log(root, record)
    rows = build(root)
    status = build_status(root, record, rows)
    write_status(root, status)
    return status
