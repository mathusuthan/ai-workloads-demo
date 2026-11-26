"""Tables for the Category 1 four-cell experiment.

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat1_ablation.py

Reads experiments/cat1_ablation/runs.jsonl and extractions.jsonl (either may be absent); writes
<project>/analysis/cat1_ablation.md and .json. Factual tables only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat1_triage import ablation as ab  # noqa: E402

DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat1_ablation.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default=str(ab.RUNS_PATH))
    ap.add_argument("--extractions", default=str(ab.EXTRACTIONS_PATH))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    ap.add_argument("--out-json", default=None, help="default: --out-md with a .json suffix")
    args = ap.parse_args(argv)
    runs = ab.load_jsonl(args.runs)
    extractions = ab.load_jsonl(args.extractions)
    summary = ab.analyse(runs, extractions)
    out_md = Path(args.out_md)
    out_json = Path(args.out_json) if args.out_json else out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(ab.render_markdown(summary), encoding="utf-8")
    out_json.write_text(json.dumps(summary, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    dq = summary["data_quality"]
    print(f"Wrote {out_md} and {out_json}: {dq['ok_current_runs']}/{summary['design']['planned_runs']} current ok runs, "
          f"{dq['extraction_ok_current']}/{dq['extractions_planned']} extractions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
