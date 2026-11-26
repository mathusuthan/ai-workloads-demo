"""Rebuild replays/cat2_golden_replays.json and replays/cat2_quality_summary.json from the Category 2 experiment.

Golden replays: a fixed, pre-declared mapping (never chosen by outcome), repeat_index 0 of each cell on all 4
documents:

    unbounded            x Sonnet -> sonnet_unbounded     (max_tokens 8,000)
    unbounded            x Haiku  -> haiku_unbounded      (max_tokens 8,000)
    template_not_stated  x Sonnet -> sonnet_templated     (section template + JSON schema, max_tokens 3,000)
    template_not_stated  x Haiku  -> haiku_templated

A cell without its repeat-0 draft is left out of the replays (the app reports it as "run pending"). Each rung keeps the
schema the app reads, the response text, the real stop reason, thinking tokens, the cap and provenance.

`section_regens` comes from experiments/cat2_not_stated/section_regens.jsonl (scripts/capture_cat2_section_regens.py):
for every preset x templated model x section, the current ok record made on the templated draft written here (same
prompt, payload and schema hashes). If some but not all 32 have a current record, nothing is written and the command
exits 1. Only while that file has no records at all is the block already in the golden file kept, with a warning.

The summary comes from `not_stated_experiment.build_app_summary()` (the analysis code path).

Inputs are only read. A file whose content is unchanged is not rewritten.

Usage (from backend/):
    .venv/bin/python scripts/build_cat2_golden_from_experiment.py
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
from app.archetypes.cat2_drafting import quality_scoring as qs  # noqa: E402
from app.archetypes.cat2_drafting import section_regen_capture as rc  # noqa: E402

GOLDEN_SOURCE = "cat2_experiment_repeat0"


def current_drafts(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Latest ok record per planned draft made with the current prompt and schema."""
    plan = {p["draft_id"]: p for p in ns.plan_drafts()}
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        p = plan.get(r.get("draft_id"))
        if r.get("status") == "ok" and p and (r.get("system_sha256"), r.get("schema_sha256")) == (p["system_sha256"], p["schema_sha256"]):
            out[r["draft_id"]] = r
    return out


def convert(rec: dict[str, Any]) -> dict[str, Any]:
    text = str(rec.get("raw_text") or "")
    if rec["arm"] == ns.ARM_UNBOUNDED:
        sd: dict[str, Any] = {"mode": "unbounded_longform_prose", "char_length": len(text)}
    else:
        sd = rec.get("structured_draft") or {}
    return {
        "model_id": rec["model_id"],
        "provider": "Anthropic",
        "latency_ms": int(rec.get("latency_ms") or 0),
        "input_tokens": int(rec["input_tokens"]),
        "output_tokens": int(rec["output_tokens"]),
        "thinking_tokens": int(rec.get("thinking_tokens") or 0),
        "stop_reason": rec.get("stop_reason"),
        "max_tokens": int(rec["max_tokens"]),
        "request_params": rec.get("request_params"),
        "structured_draft": sd,
        "raw_markdown": text,
    }


def build_golden(records: list[dict[str, Any]], existing: dict[str, Any], regen_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """`regen_records` None or empty keeps the existing `section_regens` block; otherwise every planned regeneration
    needs a current record (ValueError if not)."""
    cur = current_drafts(records)
    presets: dict[str, Any] = {}
    for pid in qs.PRESET_IDS:
        rungs, prov = {}, {}
        for (arm, m), rung in ns.APP_RUNG.items():
            rec = cur.get(ns.draft_id(pid, m, arm, ns.GOLDEN_REPEAT_INDEX))
            if rec is None:
                continue
            rungs[rung] = convert(rec)
            prov[rung] = {"draft_id": rec["draft_id"], "arm": arm, "model_key": m, "repeat_index": rec["repeat_index"]}
        order = ("sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated")
        presets[pid] = {"rungs": {k: rungs[k] for k in order if k in rungs}, "provenance": {k: prov[k] for k in order if k in prov}}
    doc = {
        "provenance": {"source": GOLDEN_SOURCE, "repeat_index": ns.GOLDEN_REPEAT_INDEX, "drafts_file": "experiments/cat2_not_stated/drafts.jsonl",
                       "pending_rungs": sorted({r for pid in qs.PRESET_IDS for r in ns.APP_RUNG.values() if r not in presets[pid]["rungs"]})},
        "presets": presets,
    }
    if regen_records:
        doc["section_regens"] = rc.build_section_regens_block(rc.plan_regens(doc), regen_records)
        doc["provenance"]["section_regens_file"] = rc.REGENS_FILE_LABEL
    else:
        doc["section_regens"] = existing.get("section_regens") or {}
    return doc


def _write(path: Path, doc: dict[str, Any]) -> bool:
    new = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == new:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", default=str(ns.DRAFTS_PATH))
    ap.add_argument("--judgements", default=str(ns.JUDGEMENTS_PATH))
    ap.add_argument("--out", default=str(qs.REPLAYS_PATH))
    ap.add_argument("--summary-out", default=str(ns.APP_SUMMARY_PATH))
    ap.add_argument("--regens", default=str(rc.REGENS_PATH))
    args = ap.parse_args(argv)
    drafts, judgements = ns.load_jsonl(args.drafts), ns.load_jsonl(args.judgements)
    out = Path(args.out)
    existing = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    regen_records = rc.load_records(args.regens)
    try:
        golden = build_golden(drafts, existing, regen_records)
    except (ValueError, rc.BaseDraftMissing) as exc:
        print(f"Not written: section regenerations incomplete for the current drafts: {exc}\n"
              "Run scripts/capture_cat2_section_regens.py (it sends only the missing or stale keys), then rebuild.", file=sys.stderr)
        return 1
    if not regen_records:
        print(f"WARNING: {Path(args.regens).name} has no records; the section_regens block already in {out.name} is kept "
              "(it was not captured on these drafts). Run scripts/capture_cat2_section_regens.py.")
    summary = ns.build_app_summary(drafts, judgements, source_files={"drafts": "backend/experiments/cat2_not_stated/drafts.jsonl",
                                                                     "judgements": "backend/experiments/cat2_not_stated/judgements.jsonl"})
    for path, doc in ((out, golden), (Path(args.summary_out), summary)):
        print(f"{'Wrote' if _write(path, doc) else 'Unchanged'} {path}")
    for c in summary["cells"]:
        print(f"  {c['rung_id']:<18} {c['status']:<8} drafts {c['drafts']}/{c['drafts_planned']} judged {c['judged_drafts']}")
    print(f"  head-to-head: {summary['head_to_head']['status']} ({summary['counts']['pairwise_calls']}/{summary['counts']['pairwise_planned']} calls)")
    print(f"  pending golden rungs: {golden['provenance']['pending_rungs']}")
    n_regen = sum(len(m) for secs in golden["section_regens"].values() for m in secs.values())
    print(f"  section regenerations: {n_regen} ({'from ' + rc.REGENS_FILE_LABEL if regen_records else 'kept from the existing file'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
