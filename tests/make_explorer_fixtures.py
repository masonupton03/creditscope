"""Regenerate tests/fixtures/explorer_expected.json from the committed sample data using the
independent Python implementation (tests/ref_finance.py).

    python tests/make_explorer_fixtures.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ref_finance as ref  # noqa: E402

SAMPLE = HERE.parent / "explorer" / "sample"
OUT = HERE / "fixtures" / "explorer_expected.json"


def load_series():
    index = json.loads((SAMPLE / "index.json").read_text())
    return {e["s"]: json.loads((SAMPLE / "series" / (e["s"] + ".json")).read_text()) for e in index["entries"]}


def build_expected(series=None):
    series = series or load_series()
    spy = series["SPY"]
    out = {"periods": ref.PERIODS, "summaries": {}}
    for sym, s in series.items():
        out["summaries"][sym] = {}
        for period in ref.PERIODS:
            summary = ref.summarize(s, period, None if sym == "SPY" else spy)
            comp = summary.get("compare")
            if comp and "series" in comp:                      # keep fixtures small: checkpoints instead of full arrays
                ser = comp.pop("series")
                n = len(ser["dates"])
                keep = sorted({0, n // 3, (2 * n) // 3, n - 1})
                comp["checkpoints"] = {"n": n, "at": keep, "dates": [ser["dates"][i] for i in keep],
                                       "a": [ser["a"][i] for i in keep], "b": [ser["b"][i] for i in keep],
                                       "relative": [ser["relative"][i] for i in keep]}
            out["summaries"][sym][period] = summary
    return out


if __name__ == "__main__":
    OUT.write_text(json.dumps(build_expected(), separators=(",", ":"), sort_keys=True) + "\n")
    print("wrote", OUT, OUT.stat().st_size, "bytes")
