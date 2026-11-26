"""Build replays/cat2_not_stated_summary.json — the "Not stated in source" follow-up as the app shows it.

Usage (from backend/):
    .venv/bin/python scripts/build_cat2_not_stated_summary.py

Offline. Same code path as scripts/analyze_cat2_not_stated.py (`not_stated_experiment.analyse()`), reduced by
`not_stated_experiment.build_app_summary()`. No timestamps, so a rebuild with unchanged inputs leaves the file
byte-identical (and does not rewrite it). The experiment files are only read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat2_drafting import not_stated_experiment as ns  # noqa: E402


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(BACKEND_DIR))
    except ValueError:
        return Path(p).name


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_if_changed(doc: dict[str, Any], out_path: Path) -> bool:
    text = render(doc)
    if out_path.is_file() and out_path.read_text(encoding="utf-8") == text:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", default=str(ns.DRAFTS_PATH))
    ap.add_argument("--judgements", default=str(ns.JUDGEMENTS_PATH))
    ap.add_argument("--out", default=str(ns.APP_SUMMARY_PATH))
    args = ap.parse_args(argv)
    drafts, judgements = ns.load_jsonl(args.drafts), ns.load_jsonl(args.judgements)
    if not drafts or not judgements:
        raise SystemExit("Drafts and judge records are both required.")
    doc = ns.build_app_summary(drafts, judgements, source_files={"drafts": _rel(Path(args.drafts)), "judgements": _rel(Path(args.judgements))})
    out = Path(args.out)
    wrote = write_if_changed(doc, out)
    cells = "; ".join(f"{c['arm']}/{c['model_key']} serious {c['serious_per_draft']:.2f}" for c in doc["cells"])
    print(f"{'Wrote' if wrote else 'Unchanged'} {out} ({doc['counts']['drafts']} drafts, {doc['counts']['judge_ok_calls']} judge calls; {cells}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
