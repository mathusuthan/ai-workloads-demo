"""Summarise Category 5 ablation records into analysis/cat5_ablation.md and .json (offline, no API calls).

Usage (from backend/):
    .venv/bin/python scripts/analyze_cat5_ablation.py
    .venv/bin/python scripts/analyze_cat5_ablation.py --in path/to/runs.jsonl --repeats 3

Runs with zero records (all tables show n/a). The records file is only read, never rewritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat5_orchestration.ablation import ARM_IDS, load_jsonl, render_markdown, summarise  # noqa: E402
from app.data.cat5_ablation_fixtures import CAT5_ABLATION_DEFAULT_INVOICE_IDS  # noqa: E402

DEFAULT_IN = BACKEND_DIR / "experiments" / "cat5_ablation" / "runs.jsonl"
DEFAULT_OUT_MD = PROJECT_DIR / "analysis" / "cat5_ablation.md"


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN), help="runs.jsonl path")
    ap.add_argument("--out-md", default=str(DEFAULT_OUT_MD), help="markdown output (JSON written beside it)")
    ap.add_argument("--repeats", type=int, default=None, help="expected repeats (default: inferred from records)")
    ap.add_argument("--arms", default="", help="comma list (default all arms)")
    ap.add_argument("--invoices", default="", help="comma list (default: the default matrix)")
    args = ap.parse_args(argv)

    records = load_jsonl(args.inp)
    summary = summarise(
        records,
        arm_ids=_csv(args.arms) if args.arms else list(ARM_IDS),
        preset_ids=_csv(args.invoices) if args.invoices else list(CAT5_ABLATION_DEFAULT_INVOICE_IDS),
        expected_repeats=args.repeats,
    )
    md_path = Path(args.out_md)
    json_path = md_path.with_suffix(".json")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Read {len(records)} records from {args.inp}; used {summary['ok_runs_used']} ok runs.")
    print(f"Wrote {md_path} and {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
