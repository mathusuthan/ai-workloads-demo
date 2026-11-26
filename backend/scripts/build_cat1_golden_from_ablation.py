"""Rebuild replays/cat1_golden_replays.json and replays/cat1_ablation_summary.json from the Category 1 ablation.

Golden replays — fixed, pre-declared mapping (never chosen by outcome): repeat_index 0 of the four ablation arms that
match the app's runnable rungs, on all 12 items (the 6 presets and the 6 batch items):

    sonnet_report    -> sonnet_naive        (today's write-up prompt, max_tokens 8,192)
    haiku_report     -> haiku_naive         (same prompt on Haiku, max_tokens 8,192)
    haiku_schema     -> haiku_calibrated    (today's calibrated prompt + JSON schema, max_tokens 512)
    gemini_decision  -> gemini_decision     (today's decisions call)

Each rung keeps the schema the app reads (presets: `presets[id].rungs[rung]`; batch items: the flat keys
`runner.execute_cat1_batch` reads, plus the same per-rung records under `batch_items[id].rungs`), with the full
response text, the real stop reason, thinking tokens, the cap the run used and provenance. For the two write-up rungs
the reader model's extraction (the ablation's blind extraction judge) is stored beside the text; the app scores
replayed write-ups from it.

Before the golden file is replaced for the first time it is copied verbatim to replays/cat1_original_capture.json
(the "original capture" group of the analysis); afterwards that copy is only read. The summary comes from the same
`ablation.summarise()` path as scripts/analyze_cat1_ablation.py.

Inputs are only read. A file whose content is unchanged (ignoring `provenance.rebuilt_at`) is not rewritten.

Usage (from backend/):
    .venv/bin/python scripts/build_cat1_golden_from_ablation.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.archetypes.cat1_triage import ablation as ab  # noqa: E402
from app.archetypes.cat2_drafting import quality_scoring as qs  # noqa: E402

DEFAULT_RUNS = ab.RUNS_PATH
DEFAULT_EXTRACTIONS = ab.EXTRACTIONS_PATH
DEFAULT_OUT = ab.GOLDEN_PATH
DEFAULT_SUMMARY_OUT = ab.SUMMARY_PATH
DEFAULT_ORIGINAL = ab.ORIGINAL_CAPTURE_PATH
PROVIDER = {"sonnet_naive": "Anthropic", "haiku_naive": "Anthropic", "haiku_calibrated": "Anthropic",
            "gemini_decision": "Google Gemini Decisions API"}


def select_record(runs: dict[str, dict[str, Any]], arm_id: str, item_id: str) -> dict[str, Any]:
    """Latest ok record at the current settings for (arm, item, repeat 0) — the analysis' rule."""
    rec = runs.get(ab.run_id(arm_id, item_id, ab.GOLDEN_REPEAT_INDEX))
    if rec is None:
        raise ValueError(f"no current ok record for {arm_id} / {item_id} / r{ab.GOLDEN_REPEAT_INDEX}")
    return rec


def reader_extraction(rec: dict[str, Any], extractions: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    e = extractions.get(ab.extraction_call_id("run", rec["run_id"]))
    if not e:
        return None
    return {
        "source": "reader_model",
        "reader_model": e.get("model_id") or qs.JUDGE_MODEL,
        "call_id": e["call_id"],
        "extracted_at": e.get("finished_at"),
        "values": ab.extracted_values(e["parsed"], rec["sub_task"]),
        "fields": e["parsed"]["fields"],
        "note": ("Read by a model that was not under test and never saw the right answer; it reports what the response says "
                 "(an allowed label, not_stated or ambiguous) with a verbatim quote."),
    }


def convert_record(rec: dict[str, Any], extractions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rung_id = ab.APP_RUNG_FOR_ARM[rec["arm_id"]]
    settings = rec.get("settings") or {}
    out: dict[str, Any] = {
        "model_id": rec["model_returned"],
        "provider": PROVIDER[rung_id],
        "latency_ms": int(rec["latency_ms"]),
        "input_tokens": int(rec["input_tokens"]),
        "output_tokens": int(rec["output_tokens"]),
        "thinking_tokens": int(rec.get("thinking_tokens") or 0),
        "stop_reason": rec.get("stop_reason"),
        "truncated": bool(rec.get("truncated")),
        "max_tokens": settings.get("max_tokens"),
        "request_params": rec.get("request_params") or ({"api_version": "v1beta"} if rung_id == "gemini_decision" else None),
    }
    if rung_id in ("sonnet_naive", "haiku_naive"):
        text = rec.get("raw_text") or ""
        out.update({"structured_output": {"mode": "unstructured_chat_prose", "char_length": len(text)}, "raw_text_preview": text,
                    "decision_probabilities": None, "reader_extraction": reader_extraction(rec, extractions)})
    elif rung_id == "haiku_calibrated":
        out.update({"structured_output": dict(rec.get("structured_output") or {}), "raw_text_preview": rec.get("raw_text"),
                    "decision_probabilities": None, "schema_parse_ok": bool(rec.get("schema_parse_ok"))})
    else:
        dec = rec.get("decision") or {}
        out.update({"structured_output": dict(rec.get("structured_output") or {}), "raw_text_preview": None,
                    "decision_probabilities": dict(dec.get("decision_probabilities") or {}), "endpoint": dec.get("endpoint"),
                    "input_tokens_possibly_estimated": bool(dec.get("input_tokens_possibly_estimated"))})
    return out


def _provenance(rec: dict[str, Any]) -> dict[str, Any]:
    return {"arm_id": rec["arm_id"], "run_id": rec["run_id"], "repeat_index": int(rec["repeat_index"]), "started_at": rec.get("started_at"),
            "settings_sha256": rec.get("settings_sha256"), "system_prompt_sent_sha256": rec.get("system_prompt_sent_sha256"),
            "settings": rec.get("settings")}


def _flat_batch(rungs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The flat keys runner.execute_cat1_batch (and older readers) use for a batch item."""
    s, hn, h, g = rungs["sonnet_naive"], rungs["haiku_naive"], rungs["haiku_calibrated"], rungs["gemini_decision"]
    confs = [float(v.get("confidence", 0.0)) for v in (g.get("decision_probabilities") or {}).values()]
    return {
        "input_tokens": h["input_tokens"], "haiku_output_tokens": h["output_tokens"], "haiku_latency_ms": h["latency_ms"],
        "haiku_decision": h["structured_output"],
        "gemini_decision": g["structured_output"], "gemini_input_tokens": g["input_tokens"], "gemini_latency_ms": g["latency_ms"],
        "gemini_confidence": round(statistics.fmean(confs), 3) if confs else 0.0,
        "sonnet_raw_text": s["raw_text_preview"], "sonnet_input_tokens": s["input_tokens"], "sonnet_output_tokens": s["output_tokens"],
        "sonnet_latency_ms": s["latency_ms"],
        "haiku_naive_raw_text": hn["raw_text_preview"], "haiku_naive_input_tokens": hn["input_tokens"],
        "haiku_naive_output_tokens": hn["output_tokens"], "haiku_naive_latency_ms": hn["latency_ms"],
    }


def build_golden(run_records: list[dict[str, Any]], extraction_records: list[dict[str, Any]], *, source_files: dict[str, str],
                 golden: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    runs = ab.latest_ok_current(run_records)
    plan = ab.plan_extractions(ab.extraction_targets(runs, golden))
    extractions = ab.latest_ok_extractions(extraction_records, plan)
    presets: dict[str, Any] = {}
    batch: dict[str, Any] = {}
    run_ids: dict[str, dict[str, str]] = {}
    for item in ab.ITEMS:
        iid = item["id"]
        rungs, prov = {}, {}
        for arm_id, rung_id in ab.APP_RUNG_FOR_ARM.items():
            rec = select_record(runs, arm_id, iid)
            rungs[rung_id] = convert_record(rec, extractions)
            prov[rung_id] = _provenance(rec)
            run_ids.setdefault(iid, {})[rung_id] = rec["run_id"]
        if item["group"] == "preset":
            presets[iid] = {"sub_task": item["sub_task"], "rungs": rungs, "provenance": prov}
        else:
            batch[iid] = {**_flat_batch(rungs), "sub_task": item["sub_task"], "rungs": rungs, "provenance": prov}
    doc = {
        "provenance": {
            "source": ab.ABLATION_GOLDEN_SOURCE,
            "source_files": source_files,
            "selection_rule": (f"fixed pre-declared mapping: repeat_index {ab.GOLDEN_REPEAT_INDEX} of "
                               + ", ".join(f"{a} -> {r}" for a, r in ab.APP_RUNG_FOR_ARM.items())
                               + " on all 12 items (not selected by outcome)"),
            "settings_note": (f"Write-up rungs ran at max_tokens {ab.CAPS['report']}, the schema rung at {ab.CAPS['schema']}; thinking as the app "
                              "sets it (Sonnet between_tools, Haiku disabled); max_retries 0; stop_reason values are as returned by the API "
                              "(the decisions API has none)."),
            "accuracy_note": ("Write-up rungs carry the reader model's extraction (`reader_extraction`); the app scores replayed write-ups from it. "
                              "The write-up prompt never lists the allowed labels, so this measures whether one allowed label can be read off "
                              "the write-up and is right."),
            "original_capture": "replays/cat1_original_capture.json (verbatim copy of the golden replays before this rebuild)",
        },
        "presets": presets,
        "batch_items": batch,
    }
    return doc, run_ids


def _comparable(doc: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(doc))
    (out.get("provenance") or {}).pop("rebuilt_at", None)
    return out


def write_if_changed(doc: dict[str, Any], out_path: Path, *, stamp: bool) -> bool:
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
        if existing is not None and _comparable(existing) == _comparable(doc):
            return False
    out_doc = dict(doc)
    if stamp:
        out_doc["provenance"] = {**doc["provenance"], "rebuilt_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def ensure_original_capture(golden_path: Path, original_path: Path) -> bool:
    """Copy the golden file verbatim to `original_path` once, while it is still the original capture."""
    if original_path.is_file():
        return False
    if not golden_path.is_file():
        raise SystemExit(f"neither {original_path} nor {golden_path} exists; the original capture is needed")
    if ab.is_ablation_golden(json.loads(golden_path.read_text(encoding="utf-8"))):
        raise SystemExit(f"{golden_path} is already rebuilt from the ablation and {original_path} is missing; restore it from a backup")
    shutil.copyfile(golden_path, original_path)
    return True


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(BACKEND_DIR))
    except ValueError:
        return str(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default=str(DEFAULT_RUNS))
    ap.add_argument("--extractions", default=str(DEFAULT_EXTRACTIONS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT))
    ap.add_argument("--original", default=str(DEFAULT_ORIGINAL))
    args = ap.parse_args(argv)
    runs_path, ext_path = Path(args.runs), Path(args.extractions)
    out_path, summary_path, original_path = Path(args.out), Path(args.summary_out), Path(args.original)
    copied = ensure_original_capture(out_path, original_path)
    original = json.loads(original_path.read_text(encoding="utf-8"))
    run_records, extraction_records = ab.load_jsonl(runs_path), ab.load_jsonl(ext_path)
    sources = {"runs": _rel(runs_path), "extractions": _rel(ext_path), "original_capture": _rel(original_path)}
    golden, run_ids = build_golden(run_records, extraction_records, source_files=sources, golden=original)
    portfolio = ab.build_ablation_portfolio(run_records, extraction_records, golden=original, source_files=sources, golden_run_ids=run_ids)
    changed_s = write_if_changed(portfolio, summary_path, stamp=False)
    changed_g = write_if_changed(golden, out_path, stamp=True)
    if copied:
        print(f"Copied the original capture to {original_path}")
    for group in ("presets", "batch_items"):
        for iid, p in golden[group].items():
            for rid, rung in p["rungs"].items():
                prov = p["provenance"][rid]
                ext = rung.get("reader_extraction")
                print(f"{iid} {rid:<17} <- {prov['run_id']:<28} stop={rung['stop_reason']} out={rung['output_tokens']:>5} "
                      f"cap={rung['max_tokens']}{' reader=' + str(sum(v is not None for v in ext['values'].values())) + ' stated' if ext else ''}")
    print(f"{'Wrote' if changed_g else 'Unchanged:'} {out_path}")
    for a in portfolio["arms"]:
        print(f"  {a['arm_id']:<21} fields {a['fields_correct']}/{a['fields_total']} items {a['items_fully_correct']}/{a['items']} "
              f"${a['cost_per_1k_items_usd']:.3f}/1k")
    print(f"  pending: " + "; ".join(f"{k} {v['done']}/{v['planned']} ({v['status']})" for k, v in portfolio["pending"].items()))
    print(f"{'Wrote' if changed_s else 'Unchanged:'} {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
