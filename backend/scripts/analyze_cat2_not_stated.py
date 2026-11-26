"""Tables for the Category 2 "Not stated in source" follow-up experiment.

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat2_not_stated.py

Reads experiments/cat2_not_stated/drafts.jsonl, the judge JSONL if present, and (read-only, for a separate context
table) replays/cat2_quality_summary.json; writes <project>/analysis/cat2_not_stated.md and .json. Factual tables only.
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

DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat2_not_stated.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", default=str(ns.DRAFTS_PATH))
    ap.add_argument("--judgements", default=str(ns.JUDGEMENTS_PATH))
    ap.add_argument("--baseline", default=str(ns.BASELINE_SUMMARY_PATH))
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    ap.add_argument("--out-json", default=None, help="default: --out-md with a .json suffix")
    args = ap.parse_args(argv)
    drafts = ns.load_jsonl(args.drafts)
    judgements = ns.load_jsonl(args.judgements)
    summary = ns.analyse(drafts, judgements or None, baseline_summary=ns.load_baseline_summary(args.baseline))
    out_md = Path(args.out_md)
    out_json = Path(args.out_json) if args.out_json else out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(ns.render_markdown(summary), encoding="utf-8")
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_md} and {out_json} ({summary['drafts_data_quality']['ok_drafts']} drafts, {len(judgements)} judge records).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
