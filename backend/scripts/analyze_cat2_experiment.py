"""Tables for the Category 2 experiment (unbounded draft vs section template, on Sonnet 5.5 and Haiku 5.5).

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat2_experiment.py

Reads experiments/cat2_not_stated/drafts.jsonl and judgements.jsonl (either may be absent); writes
<project>/analysis/cat2_quality.md and .json. Factual tables only; cells without drafts show "run pending".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat2_drafting import not_stated_experiment as ns  # noqa: E402

DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat2_quality.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", default=str(ns.DRAFTS_PATH))
    ap.add_argument("--judgements", default=str(ns.JUDGEMENTS_PATH))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    ap.add_argument("--out-json", default=None, help="default: --out-md with a .json suffix")
    args = ap.parse_args(argv)
    s = ns.analyse(ns.load_jsonl(args.drafts), ns.load_jsonl(args.judgements))
    out_md = Path(args.out_md)
    out_json = Path(args.out_json) if args.out_json else out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(ns.render_markdown(s), encoding="utf-8")
    out_json.write_text(json.dumps(s, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    dq = s["drafts_data_quality"]
    print(f"Wrote {out_md} and {out_json}: {dq['ok_drafts']}/{s['design']['planned_drafts']} drafts; head-to-head {s['pairwise']['status']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
