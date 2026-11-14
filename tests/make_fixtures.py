"""Regenerate tests/fixtures/sample/{history.csv,status.json,expected.json}.

    python tests/make_fixtures.py

expected.json comes from the independent Python implementation in ref_stats.py; the Node test
checks that assets/js/stats.js (the code the Trends page runs) produces the same numbers.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ref_stats  # noqa: E402
import sample_data  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures" / "sample"


def build(out: Path):
    with tempfile.TemporaryDirectory() as tmp:
        sample_data.write_sample(Path(tmp))
        out.mkdir(parents=True, exist_ok=True)
        for name in ("history.csv", "status.json"):
            (out / name).write_bytes((Path(tmp) / "data" / name).read_bytes())
    expected = ref_stats.report(ref_stats.read(out / "history.csv"))
    (out / "expected.json").write_text(json.dumps(expected, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    build(OUT)
    print("fixtures written to", OUT)
