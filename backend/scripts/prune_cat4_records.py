#!/usr/bin/env python3
"""Keep only the current Category 4 quality-rerun records (deterministic, idempotent).

runs.jsonl                     latest ok session per (rung, scale, repeat) of the two displayed versions
                               (`quality_rerun.RUNG_IDS`: without and with the deck's lever), recorded at the
                               current synthesis cap and in the rung's answer format; everything else is dropped.
judgements.jsonl               latest ok rerun judgement per call id whose answer (run id + question + answer hash)
                               belongs to a kept session; everything else is dropped.
other_levers/runs.jsonl        the same rule for the other levers that were run (`OTHER_LEVER_RECORD_FORMATS`:
other_levers/judgements.jsonl  cached full corpus with citations; retrieval + rerank without a cache, whose code was
                               removed after commit 7807557), moved out of the main files. Nothing displayed reads them.
runs.pilot_cap2048.jsonl       deleted.

Usage:
  .venv/bin/python scripts/prune_cat4_records.py --dry-run
  .venv/bin/python scripts/prune_cat4_records.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat4_rag.answer_formats import SCOPED_ABSENCE, record_answer_format, rung_answer_format  # noqa: E402
from app.archetypes.cat4_rag.quality_rerun import OTHER_LEVER_RUNG_IDS, RUNG_IDS  # noqa: E402

EXPERIMENT_DIR = BACKEND_DIR / "experiments" / "cat4_quality"
SYNTH_MAX_TOKENS = 4096
# Other-lever records kept in other_levers/ and the answer format each was recorded with. The retrieval-without-cache
# lever is listed here although the harness no longer runs it, so re-running this script keeps its records.
OTHER_LEVER_RECORD_FORMATS: dict[str, str] = {
    **{r: rung_answer_format(r) for r in OTHER_LEVER_RUNG_IDS},
    "hybrid_rag_rerank_citations": SCOPED_ABSENCE,
}


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _dedupe(rows: list[dict], key: str) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        if r.get(key) not in seen:
            seen.add(r.get(key))
            out.append(r)
    return out


def keep_runs(runs: list[dict], rung_ids: tuple[str, ...] = RUNG_IDS, formats: dict[str, str] | None = None) -> list[dict]:
    want = formats or {r: rung_answer_format(r) for r in rung_ids}
    latest: dict[tuple, dict] = {}
    for r in runs:
        st = r.get("settings") or {}
        if (r.get("status") == "ok" and r.get("rung_id") in want and st.get("synth_max_tokens") == SYNTH_MAX_TOKENS
                and record_answer_format(r) == want[str(r.get("rung_id"))]):
            latest[(r["rung_id"], int(r["scale"]), int(r["repeat_index"]))] = r
    kept_ids = {id(v) for v in latest.values()}
    return _dedupe([r for r in runs if id(r) in kept_ids], "run_id")  # file order preserved


def keep_judgements(judgements: list[dict], runs: list[dict]) -> list[dict]:
    answers = {(r["run_id"], a["preset_id"], a["question_id"]): _sha(a.get("answer_markdown") or "")
               for r in runs for a in r.get("answers") or [] if a.get("status") == "ok"}
    latest: dict[str, dict] = {}
    for j in judgements:
        key = (j.get("run_id"), j.get("preset_id"), j.get("question_id"))
        if (j.get("status") == "ok" and j.get("source") == "rerun" and key in answers
                and j.get("answer_sha256") == answers[key]):
            latest[j["call_id"]] = j
    kept_ids = {id(v) for v in latest.values()}
    return _dedupe([j for j in judgements if id(j) in kept_ids], "call_id")


def split(runs: list[dict], judgements: list[dict], other_runs: list[dict], other_judgements: list[dict]):
    """(main runs, main judgements, other-lever runs, other-lever judgements). Records already moved are kept."""
    main_r = keep_runs(runs, RUNG_IDS)
    main_j = keep_judgements(judgements, main_r)
    oth_r = keep_runs([*other_runs, *runs], tuple(OTHER_LEVER_RECORD_FORMATS), OTHER_LEVER_RECORD_FORMATS)
    oth_j = keep_judgements([*other_judgements, *judgements], oth_r)
    return main_r, main_j, oth_r, oth_j


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(EXPERIMENT_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    d = Path(args.dir)
    runs_p, judg_p, pilot_p = d / "runs.jsonl", d / "judgements.jsonl", d / "runs.pilot_cap2048.jsonl"
    oruns_p, ojudg_p = d / "other_levers" / "runs.jsonl", d / "other_levers" / "judgements.jsonl"
    runs, judgements, oruns, ojudg = _read(runs_p), _read(judg_p), _read(oruns_p), _read(ojudg_p)
    kept_r, kept_j, new_or, new_oj = split(runs, judgements, oruns, ojudg)
    answers = sum(1 for r in kept_r for a in r.get("answers") or [] if a.get("status") == "ok")
    print(f"runs.jsonl: {len(runs)} -> {len(kept_r)} ({len(runs) - len(kept_r)} removed; {answers} answers kept)")
    print(f"judgements.jsonl: {len(judgements)} -> {len(kept_j)} ({len(judgements) - len(kept_j)} removed)")
    print(f"other_levers/runs.jsonl: {len(oruns)} -> {len(new_or)}")
    print(f"other_levers/judgements.jsonl: {len(ojudg)} -> {len(new_oj)}")
    print(f"runs.pilot_cap2048.jsonl: {'delete' if pilot_p.exists() else 'absent'}")
    if args.dry_run:
        return 0
    for path, old, new in ((oruns_p, oruns, new_or), (ojudg_p, ojudg, new_oj), (runs_p, runs, kept_r), (judg_p, judgements, kept_j)):
        if new != old:
            _write(path, new)
    if pilot_p.exists():
        pilot_p.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
