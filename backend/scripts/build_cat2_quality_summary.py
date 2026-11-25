"""Build replays/cat2_quality_summary.json — the Category 2 quality picture the app and the deck validator read.

Usage (from backend/):
    .venv/bin/python scripts/build_cat2_quality_summary.py

Offline. Same code path as scripts/analyze_cat2_quality.py: answer key + golden replays + the blind-judge
JSONL, aggregated by `quality_scoring.summarise()`, then reduced to a compact per-draft / pooled view by
`quality_scoring.build_app_summary()`. The file has no timestamps, so a rebuild with unchanged inputs leaves it
byte-identical (and is not rewritten). Judgements are read-only here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat2_drafting.quality_scoring import (  # noqa: E402
    JUDGEMENTS_PATH,
    KEYS_PATH,
    REPLAYS_PATH,
    build_app_summary,
    load_judgements,
    load_quality_keys,
    load_replays,
    run_deterministic,
)

DEFAULT_OUT = BACKEND_DIR / "replays" / "cat2_quality_summary.json"


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(BACKEND_DIR))
    except ValueError:
        return Path(p).name


def build(replays_path: Path, keys_path: Path, judgements_path: Path) -> dict[str, Any]:
    replays = load_replays(replays_path)
    det = run_deterministic(replays, load_quality_keys(keys_path))
    judgements = load_judgements(judgements_path)
    if not judgements:
        raise SystemExit(f"No judge records in {judgements_path}; nothing to summarise.")
    return build_app_summary(
        det,
        judgements,
        replays,
        source_files={
            "replays": _rel(replays_path),
            "answer_key": _rel(keys_path),
            "judgements": _rel(judgements_path),
        },
    )


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_if_changed(doc: dict[str, Any], out_path: Path) -> bool:
    """Write `doc` unless the file already holds exactly the same content. Returns True when written."""
    text = render(doc)
    if out_path.is_file() and out_path.read_text(encoding="utf-8") == text:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replays", default=str(REPLAYS_PATH))
    ap.add_argument("--keys", default=str(KEYS_PATH))
    ap.add_argument("--judgements", default=str(JUDGEMENTS_PATH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    doc = build(Path(args.replays), Path(args.keys), Path(args.judgements))
    out = Path(args.out)
    wrote = write_if_changed(doc, out)
    pooled = ", ".join(f"{r['rung_id']} serious {r['serious_errors']}" for r in doc["rungs"])
    print(f"{'Wrote' if wrote else 'Unchanged'} {out} ({doc['calls']['rubric_ok']} rubric + {doc['calls']['pairwise_ok']} pairwise calls; {pooled}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
