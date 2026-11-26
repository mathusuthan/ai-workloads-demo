"""Prune the Category 2 record files to the runs behind the displayed cells.

Usage (from backend/):
    .venv/bin/python scripts/prune_cat2_records.py --dry-run
    .venv/bin/python scripts/prune_cat2_records.py
    .venv/bin/python scripts/prune_cat2_records.py --after-rerun --dry-run   # once the unbounded drafts are judged
    .venv/bin/python scripts/prune_cat2_records.py --after-rerun

Default mode:
  experiments/cat2_not_stated/drafts.jsonl      keeps the drafts of the experiment's two versions (unbounded, section
                                                template); drafts of any other arm are dropped.
  experiments/cat2_not_stated/judgements.jsonl  keeps rubric records of those drafts, the template-vs-unbounded pairwise
                                                records and, until --after-rerun, the earlier `vs_unbounded` records
                                                (not read by anything displayed); everything else is dropped.
  experiments/cat2_quality/judgements.jsonl     keeps only the rubric records of the stored unbounded drafts.
  experiments/cat2_quality/deterministic.json   keeps only the stored unbounded drafts (the judge dry run's stand-ins).

--after-rerun (refused unless all 24 unbounded drafts and all 48 template-vs-unbounded judgements are ok): also drops
the `vs_unbounded` records and deletes experiments/cat2_quality/ (superseded by the fresh unbounded drafts).

Deterministic and idempotent: kept records stay in their original order and byte-identical; a file whose content would
not change is not rewritten. Back the files up before running without --dry-run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat2_drafting import not_stated_experiment as ns  # noqa: E402
from app.archetypes.cat2_drafting import quality_scoring as qs  # noqa: E402

FIRST_ROUND_DIR = qs.EXPERIMENT_DIR
STORED_UNBOUNDED_RUNG = "sonnet_unbounded"
EARLIER_COMPARISON = "vs_unbounded"


def _lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def split_drafts(lines: list[str]) -> tuple[list[str], Counter]:
    keep, dropped = [], Counter()
    for line in lines:
        r = json.loads(line)
        if r.get("arm") in ns.ARMS:
            keep.append(line)
        else:
            dropped[f"arm {r.get('arm')}"] += 1
    return keep, dropped


def split_judgements(lines: list[str], *, after_rerun: bool) -> tuple[list[str], Counter]:
    keep, dropped = [], Counter()
    for line in lines:
        r = json.loads(line)
        m = r.get("meta") or {}
        comp = m.get("comparison")
        if comp == "rubric" and m.get("arm") in ns.ARMS:
            keep.append(line)
        elif comp == ns.COMPARISON:
            keep.append(line)
        elif comp == EARLIER_COMPARISON and not after_rerun:
            keep.append(line)
        else:
            dropped[f"{comp}{' ' + str(m.get('arm')) if comp == 'rubric' else ''}"] += 1
    return keep, dropped


def split_first_round(lines: list[str]) -> tuple[list[str], Counter]:
    keep, dropped = [], Counter()
    for line in lines:
        r = json.loads(line)
        if r.get("task") == "rubric" and r.get("rung_id") == STORED_UNBOUNDED_RUNG:
            keep.append(line)
        else:
            dropped[f"{r.get('task')} {r.get('rung_id') or ''}".strip()] += 1
    return keep, dropped


def prune_deterministic(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    out["rung_ids"] = [r for r in d.get("rung_ids") or [] if r == STORED_UNBOUNDED_RUNG]
    out["drafts"] = [c for c in d.get("drafts") or [] if c.get("rung_id") == STORED_UNBOUNDED_RUNG]
    out["rungs"] = {k: v for k, v in (d.get("rungs") or {}).items() if k == STORED_UNBOUNDED_RUNG}
    pf = []
    for f in d.get("per_fact") or []:
        hits = {k: v for k, v in (f.get("hits") or {}).items() if k == STORED_UNBOUNDED_RUNG}
        pf.append({**f, "hits": hits, "covered_by_no_draft": not any(hits.values())})
    out["per_fact"] = pf
    out["facts_covered_by_no_draft"] = [f["fact_id"] for f in pf if f["covered_by_no_draft"]]
    return out


def _write(path: Path, new: str, dry_run: bool) -> bool:
    if path.is_file() and path.read_text(encoding="utf-8") == new:
        return False
    if not dry_run:
        path.write_text(new, encoding="utf-8")
    return True


def _jsonl(kept: list[str]) -> str:
    return "".join(line + "\n" for line in kept)


def _show(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)


def rerun_complete(drafts: list[str], judgements: list[str]) -> tuple[bool, str]:
    ok_unb = {json.loads(x)["draft_id"] for x in drafts if json.loads(x).get("status") == "ok" and json.loads(x).get("arm") == ns.ARM_UNBOUNDED}
    ok_pw = {json.loads(x)["call_id"] for x in judgements if json.loads(x).get("status") == "ok"
             and (json.loads(x).get("meta") or {}).get("comparison") == ns.COMPARISON}
    need_d = sum(1 for p in ns.plan_drafts() if p["arm"] == ns.ARM_UNBOUNDED)
    need_p = ns.planned_pairwise_calls()
    return (len(ok_unb) >= need_d and len(ok_pw) >= need_p), f"{len(ok_unb)}/{need_d} unbounded drafts, {len(ok_pw)}/{need_p} pairwise judgements ok"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment-dir", default=str(ns.EXPERIMENT_DIR))
    ap.add_argument("--first-round-dir", default=str(FIRST_ROUND_DIR))
    ap.add_argument("--after-rerun", action="store_true", help="also drop the earlier vs_unbounded records and the first-round folder")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    args = ap.parse_args(argv)
    exp, first = Path(args.experiment_dir), Path(args.first_round_dir)
    verb = "would" if args.dry_run else "did"
    d_path, j_path = exp / "drafts.jsonl", exp / "judgements.jsonl"
    d_lines, j_lines = _lines(d_path), _lines(j_path)
    if args.after_rerun:
        done, why = rerun_complete(d_lines, j_lines)
        if not done:
            print(f"Refusing --after-rerun: {why}.", file=sys.stderr)
            return 2
    d_keep, d_drop = split_drafts(d_lines)
    j_keep, j_drop = split_judgements(j_lines, after_rerun=args.after_rerun)
    rows = [(d_path, d_lines, d_keep, d_drop), (j_path, j_lines, j_keep, j_drop)]
    for path, before, kept, drop in rows:
        changed = _write(path, _jsonl(kept), args.dry_run)
        print(f"{_show(path)}: {len(before)} -> {len(kept)} records" + (f"; dropped {dict(sorted(drop.items()))}" if drop else "")
              + f"; {verb} {'write' if changed else 'leave unchanged'}")
    if args.after_rerun:
        if first.is_dir():
            if not args.dry_run:
                shutil.rmtree(first)
            print(f"{_show(first)}: {verb} delete (superseded by the fresh unbounded drafts)")
        return 0
    fj = first / "judgements.jsonl"
    if fj.is_file():
        f_lines = _lines(fj)
        f_keep, f_drop = split_first_round(f_lines)
        changed = _write(fj, _jsonl(f_keep), args.dry_run)
        print(f"{_show(fj)}: {len(f_lines)} -> {len(f_keep)} records" + (f"; dropped {dict(sorted(f_drop.items()))}" if f_drop else "")
              + f"; {verb} {'write' if changed else 'leave unchanged'}")
    fd = first / "deterministic.json"
    if fd.is_file():
        d = json.loads(fd.read_text(encoding="utf-8"))
        new = prune_deterministic(d)
        changed = _write(fd, json.dumps(new, indent=2, ensure_ascii=False) + "\n", args.dry_run)
        print(f"{_show(fd)}: drafts {len(d.get('drafts') or [])} -> {len(new['drafts'])}; {verb} {'write' if changed else 'leave unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
