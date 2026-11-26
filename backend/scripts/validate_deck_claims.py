"""De-duplicated validation of the "6 Key Production AI Archetypes" deck claims.

Reads these sources and writes a JSON + Markdown report:

1. backend/traces/            -> de-duplication audit (how many traces are distinct runs)
2. backend/replays/*.json     -> the canonical dataset for Categories 1 and 2: one record per (item x rung),
                                 with per-call token counts and the model that served each call
3. backend/experiments/cat3_quality/runs.jsonl (read-only) + backend/replays/cat3_quality_summary.json
                                 (fallback analysis/cat3_quality_rerun.json)
                              -> Category 3: the quality-rerun records of the two displayed versions (without / with
                                 the deck's improvement x 2 sessions x 3 repeats) for cost and context growth;
                                 answer-key quality scores from the summary
                                 (falls back to the Category 3 golden replays if the rerun file is missing)
4. backend/experiments/cat2_not_stated/drafts.jsonl (read-only) + backend/replays/cat2_quality_summary.json
                              -> Category 2: the four cells of its without/with design (unbounded long-form draft /
                                 section template with length caps x Sonnet / Haiku, 4 documents x 3 repeats each) for
                                 cost and tokens; blind-judge, fact-key and action-plan quality from the summary; the
                                 single-section regenerations from backend/experiments/cat2_not_stated/section_regens.jsonl
                                 (read-only; only records made on the current golden template drafts count)
5. backend/experiments/cat4_quality/runs.jsonl (read-only) + backend/replays/cat4_quality_summary.json
                                 (fallback analysis/cat4_quality_rerun.json)
                              -> Category 4: the quality-rerun records of the two displayed versions (without / with
                                 the deck's improvement x 2 corpus sizes x 3 sessions of 8 questions = 96 answers) for
                                 cost and tokens; answer-key and blind-grader quality from the summary (falls back to
                                 the golden replays)
5b. backend/experiments/cat5_ablation/runs.jsonl (read-only) + backend/replays/cat5_ablation_summary.json
                                 (fallback analysis/cat5_ablation.json)
                              -> Category 5: the four displayed cells (with / without the deck's lever x Sonnet / Haiku,
                                 12 invoices x 3 repeats each; a cell with no records yet is "run pending" and the rows
                                 use the recorded cells) selected by the summary's run ids, costs recomputed from each turn's tokens;
                                 quality from the summary (falls back to the golden replays if the records cannot be read)
6. backend/experiments/cat6_fair_rerun/runs.jsonl (read-only)
                              -> Category 6: the fair-rerun records of the four displayed cells (with / without
                                 the deck's lever x models; 3 incidents x 5 repeats each; a cell with no records
                                 yet is "run pending" and the rows use the recorded cells);
                                 sandbox verdicts as stored in the records

Costs are recomputed per call from recorded token counts. Nothing is read from the
traces' own `finops` totals, because those are modelled (cold/warm) rather than billed
and some rollups mix model rates.

Stdlib only. Usage (from repo root or anywhere):
    python3 -I backend/scripts/validate_deck_claims.py
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPLAYS = BACKEND / "replays"
TRACES = BACKEND / "traces"
OUT_DIR = BACKEND.parent / "analysis"
CAT3_RERUN = BACKEND / "experiments" / "cat3_quality" / "runs.jsonl"
CAT3_QUALITY_SUMMARY = REPLAYS / "cat3_quality_summary.json"
CAT3_QUALITY_ANALYSIS = OUT_DIR / "cat3_quality_rerun.json"
CAT2_QUALITY_SUMMARY = REPLAYS / "cat2_quality_summary.json"
CAT2_DRAFTS = BACKEND / "experiments" / "cat2_not_stated" / "drafts.jsonl"
CAT2_REGENS = BACKEND / "experiments" / "cat2_not_stated" / "section_regens.jsonl"
CAT2_REGENS_PLANNED = 32  # 4 documents x 2 models x 4 sections
CAT2_ROWS = {"without": "Without: unbounded long-form draft", "with": "With: section template with length caps"}
CAT2_COLS = {"sonnet": "Sonnet 5.5", "haiku": "Haiku 5.5"}
CAT2_DESIGN = {("without", "sonnet"): "sonnet_unbounded", ("without", "haiku"): "haiku_unbounded",
               ("with", "sonnet"): "sonnet_templated", ("with", "haiku"): "haiku_templated"}
CAT2_ORDER = ["sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated"]
CAT2_RUNG_OF = {("unbounded", "sonnet"): "sonnet_unbounded", ("unbounded", "haiku"): "haiku_unbounded",
                ("template_not_stated", "sonnet"): "sonnet_templated", ("template_not_stated", "haiku"): "haiku_templated"}
CAT2_SHORT = {"sonnet_unbounded": "without, Sonnet", "haiku_unbounded": "without, Haiku",
              "sonnet_templated": "with, Sonnet", "haiku_templated": "with, Haiku"}
CAT2_DIMS = ["factual_accuracy", "coverage", "clarity", "actionability", "concision"]
CAT4_RERUN = BACKEND / "experiments" / "cat4_quality" / "runs.jsonl"
CAT4_QUALITY_SUMMARY = REPLAYS / "cat4_quality_summary.json"
CAT4_QUALITY_ANALYSIS = OUT_DIR / "cat4_quality_rerun.json"
CAT4_SYNTH_MAX_TOKENS = 4096  # records at another synthesis cap are superseded (the 2,048-cap pilot)
CAT4_APP_MAX_TOKENS_BEFORE = 2048
CAT3_RUNGS = ["naive_full_history", "prefix_cached_summarized"]  # without / with the deck's improvement
CAT4_RUNGS = ["naive_full_corpus", "cached_rerank_hybrid"]  # without / with the deck's improvement
CAT4_SCALES = [1, 3]
# Synthesis answer format per displayed version (mirror of backend/app/archetypes/cat4_rag/answer_formats.py
# RUNG_ANSWER_FORMAT; a record without settings.answer_format used "full_corpus").
CAT4_ANSWER_FORMAT = {"naive_full_corpus": "full_corpus", "cached_rerank_hybrid": "scoped_absence"}
CAT1_ABLATION = BACKEND / "experiments" / "cat1_ablation" / "runs.jsonl"
CAT1_ABLATION_SUMMARY = REPLAYS / "cat1_ablation_summary.json"
CAT1_ABLATION_ANALYSIS = OUT_DIR / "cat1_ablation.json"
CAT1_ARMS = ["sonnet_report", "sonnet_schema", "haiku_report", "haiku_schema"]
CAT1_APP_RUNG_FOR_ARM = {"sonnet_report": "sonnet_naive", "haiku_report": "haiku_naive", "sonnet_schema": "sonnet_calibrated",
                         "haiku_schema": "haiku_calibrated"}
CAT1_ARM_MODEL = {"sonnet_report": "claude-sonnet-5-5", "sonnet_schema": "claude-sonnet-5-5",
                  "haiku_report": "claude-haiku-5-5", "haiku_schema": "claude-haiku-5-5"}
# The deck's lever (rows) x models (columns), one arm per cell.
CAT1_DESIGN = {("without", "sonnet"): "sonnet_report", ("without", "haiku"): "haiku_report",
               ("with", "sonnet"): "sonnet_schema", ("with", "haiku"): "haiku_schema"}
CAT1_ROWS = {"without": "Without: four-part write-up, free text", "with": "With: classification with strict JSON schema"}
CAT1_COLS = {"sonnet": "Sonnet 5.5", "haiku": "Haiku 5.5"}
CAT5_ABLATION = BACKEND / "experiments" / "cat5_ablation" / "runs.jsonl"
CAT5_ABLATION_SUMMARY = REPLAYS / "cat5_ablation_summary.json"
CAT5_ABLATION_ANALYSIS = OUT_DIR / "cat5_ablation.json"
# the 2x2 displayed cells: without the deck's lever (Sonnet, Haiku), with it (Sonnet, Haiku-first escalating to Sonnet)
CAT5_ARMS = ["raw_free_sonnet", "raw_free_haiku", "bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate"]
# cells the ablation path needs recorded; the Haiku "without" cell may still be pending ("run pending")
CAT5_REQUIRED_ARMS = ["raw_free_sonnet", "bundle_gate_sonnet_cached", "bundle_gate_haiku_escalate"]
CAT5_APP_RUNGS = ["unbounded_sonnet_loop", "bounded_sonnet_cached_gate", "hybrid_haiku_sonnet_governed", "unbounded_haiku_loop"]
CAT5_ARM_FOR_RUNG = {"unbounded_sonnet_loop": "raw_free_sonnet", "bounded_sonnet_cached_gate": "bundle_gate_sonnet_cached",
                     "hybrid_haiku_sonnet_governed": "bundle_gate_haiku_escalate", "unbounded_haiku_loop": "raw_free_haiku"}
CAT6_RERUN = BACKEND / "experiments" / "cat6_fair_rerun" / "runs.jsonl"
# Design order: without the lever (Sonnet, Haiku agents + Sonnet patch author), then with it (same two columns).
CAT6_ARMS = ["shared_bus_matched_gate", "shared_bus_tiered_gate", "isolated_cached_gate", "tiered_gate"]
# The deck's lever (rows) x models (columns). Same instructions, caps and sandbox gate in every cell.
CAT6_DESIGN = {("without", "sonnet"): "shared_bus_matched_gate", ("without", "tiered"): "shared_bus_tiered_gate",
               ("with", "sonnet"): "isolated_cached_gate", ("with", "tiered"): "tiered_gate"}
CAT6_ROWS = {"without": "Without: shared bus, same instructions, sandbox check with one retry",
             "with": "With: isolated agents + cached repo prefix, sandbox check with one retry"}
CAT6_COLS = {"sonnet": "Sonnet 5.5", "tiered": "Haiku agents + Sonnet patch author"}
CAT6_CELL = {"shared_bus_matched_gate": "without the lever (shared bus), Sonnet",
             "shared_bus_tiered_gate": "without the lever (shared bus), Haiku agents + Sonnet patch author",
             "isolated_cached_gate": "with the lever, Sonnet",
             "tiered_gate": "with the lever, Haiku agents + Sonnet patch author"}
CAT6_RUN_PENDING = "run pending"

SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"

# $/1M tokens: (input, output, cache_write_5m, cache_read)
RATE_CARDS = {
    # Sonnet cache read at $0.20 (an earlier repo rate); only `cost_per_1k_billed_repo_card` uses it, which
    # _render_cat4 / _render_cat5 still read. Remove together with that key once they drop it.
    "repo": {
        SONNET: (2.00, 10.00, 2.50, 0.20),
        HAIKU: (0.10, 0.50, 0.125, 0.01),
    },
    # Anthropic published pricing (model table cached 2026-11-03): Sonnet 5.5 $2/$10,
    # cache reads $0.10; Haiku 5.5 $0.10/$0.50 for prompts <=100K tokens.
    # Cache writes assumed at the standard 1.25x input (5-minute TTL); Haiku cache read 0.1x.
    "official": {
        SONNET: (2.00, 10.00, 2.50, 0.10),
        HAIKU: (0.10, 0.50, 0.125, 0.01),
    },
}
HAIKU_LONG_PROMPT_THRESHOLD = 100_000  # above this Haiku 5.5 is $0.50/$2.50


# --------------------------------------------------------------------------- helpers
def call(model, inp, out, cw=0, cr=0, role=""):
    return {"model": model, "in": int(inp or 0), "out": int(out or 0), "cw": int(cw or 0), "cr": int(cr or 0), "role": role}


def call_cost(c, card="official", view="billed", first_touch=None, batch=False):
    """Cost of one call in USD.

    view = billed : cache tokens exactly as recorded by the API at capture time
           warm   : every cached-prefix token is a cache read (steady state, cache already hot)
           cold   : the first call per model in the unit writes the whole prefix, later calls read
    """
    r_in, r_out, r_cw, r_cr = RATE_CARDS[card][c["model"]]
    cw, cr = c["cw"], c["cr"]
    prefix = cw + cr
    if view == "warm":
        cw, cr = 0, prefix
    elif view == "cold" and prefix:
        if first_touch is not None and c["model"] not in first_touch:
            first_touch.add(c["model"])
            cw, cr = prefix, 0
        else:
            cw, cr = 0, prefix
    usd = (c["in"] * r_in + c["out"] * r_out + cw * r_cw + cr * r_cr) / 1e6
    return usd * (0.5 if batch else 1.0)


def unit_cost(calls, card="official", view="billed", batch=False):
    seen = set()
    return sum(call_cost(c, card, view, seen, batch) for c in calls)


def prompt_tokens(c):
    return c["in"] + c["cw"] + c["cr"]


def tok(calls):
    p = sum(prompt_tokens(c) for c in calls)
    o = sum(c["out"] for c in calls)
    return {"prompt": p, "output": o, "total": p + o, "calls": len(calls), "max_call_prompt": max((prompt_tokens(c) for c in calls), default=0)}


def output_cost_share(calls, card="official"):
    tot = unit_cost(calls, card)
    out = sum(c["out"] * RATE_CARDS[card][c["model"]][1] for c in calls) / 1e6
    return out / tot if tot else 0.0


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def rng(xs):
    xs = [x for x in xs if x is not None]
    return (min(xs), max(xs)) if xs else (None, None)


def pct_saving(base, new):
    return (1 - new / base) * 100 if base else None


def slope(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


def load(cat):
    return json.loads((REPLAYS / f"cat{cat}_golden_replays.json").read_text())


# ------------------------------------------------------------------ 1. dedup audit
def _trace_files():
    """Trace JSON files under backend/traces/, never the backups folder."""
    return [p for p in TRACES.rglob("*.json") if "_backups" not in p.relative_to(TRACES).parts]


def dedup_audit():
    recs = []
    for p in _trace_files():
        try:
            recs.append(json.loads(p.read_text()))
        except Exception:
            continue

    def fp(r):
        f, resp, part = r.get("finops") or {}, r["response"], r["partition"]
        body = resp.get("raw_text") or json.dumps(resp.get("structured_output"), sort_keys=True)
        return (
            part["category"], part["use_case"], part["model"], part["pattern"], r["item_id"],
            f.get("input_tokens"), f.get("output_tokens"), f.get("cache_creation_tokens"), f.get("cache_read_tokens"),
            hashlib.sha1(body.encode()).hexdigest()[:12],
        )

    groups = defaultdict(list)
    for r in recs:
        groups[fp(r)].append(r)
    # Only the newest seed per (category, model, pattern, item) is canonical; an older seed for the same slot
    # (e.g. the first Category 6 capture, replaced by the fair rerun) is a superseded capture.
    current_seed_ids = current_seed_trace_ids(recs)
    # token-level key of every canonical (seed) run, to catch replays of the same run re-serialised differently
    seed_token_keys = {k[:9] for k, members in groups.items() if any(m.get("trace_id") in current_seed_ids for m in members)}

    def classify(key, members):
        modes = {m["source_mode"] for m in members}
        if any(m["response"]["status"] == "error" for m in members):
            return "error (live, no tokens)"
        if any(m.get("trace_id") in current_seed_ids for m in members) or key[:9] in seed_token_keys:
            return "canonical golden-replay run"
        if "live" in modes:
            return "ad-hoc live run"
        item = members[0]["item_id"]
        if "__session" in item or "__audit" in item:
            return "rollup of canonical runs (session/audit sum)"
        return "superseded capture (older golden-replay version)"

    by_cat = defaultdict(lambda: {"raw_traces": 0, "distinct_fingerprints": 0, "classes": Counter(), "raw_by_mode": Counter()})
    for key, members in groups.items():
        b = by_cat[key[0]]
        b["raw_traces"] += len(members)
        b["distinct_fingerprints"] += 1
        b["classes"][classify(key, members)] += 1
        for m in members:
            b["raw_by_mode"][m["source_mode"]] += 1
    canon = defaultdict(set)
    for key, members in groups.items():
        if classify(key, members) == "canonical golden-replay run":
            canon[key[0]].add(key[:9])
    for cat, b in by_cat.items():
        b["canonical_runs"] = len(canon[cat])
    totals = {
        "raw_traces": len(recs),
        "distinct_fingerprints": len(groups),
        "canonical_runs": sum(b["canonical_runs"] for b in by_cat.values()),
        "raw_by_mode": dict(Counter(r["source_mode"] for r in recs)),
        "classes": dict(sum((b["classes"] for b in by_cat.values()), Counter())),
        "max_duplicates_of_one_run": max((len(v) for v in groups.values()), default=0),
    }
    return {
        "totals": totals,
        "by_category": {k: {**v, "classes": dict(v["classes"]), "raw_by_mode": dict(v["raw_by_mode"])} for k, v in sorted(by_cat.items())},
    }


def _seed_slot(r):
    part = r["partition"]
    return (part["category"], part["model"], part["pattern"], r["item_id"])


def current_seed_trace_ids(recs):
    """trace_id of the newest seed trace per (category, model, pattern, item)."""
    newest = {}
    for r in recs:
        if r.get("source_mode") != "live_captured_seed":
            continue
        k = _seed_slot(r)
        if k not in newest or (r.get("timestamp_utc", ""), r.get("trace_id", "")) > (newest[k].get("timestamp_utc", ""), newest[k].get("trace_id", "")):
            newest[k] = r
    return {r.get("trace_id") for r in newest.values()}


def seed_index():
    """Per-run quality metadata recorded on canonical (newest) seed traces."""
    recs = [json.loads(p.read_text()) for p in _trace_files()]
    current = current_seed_trace_ids(recs)
    return {_seed_slot(r): r for r in recs if r.get("trace_id") in current}


# ------------------------------------------------------------- 2. canonical units
def cat1_ablation_info():
    """Quality, levers and the record selection for the Category 1 ablation, from replays/cat1_ablation_summary.json,
    falling back to analysis/cat1_ablation.json. Returns (info, source)."""
    try:
        d = json.loads(CAT1_ABLATION_SUMMARY.read_text())
        arms = {a["arm_id"]: {"label": a["label"], "task": a["task"], "runs": a["runs"], "fields": a["fields_correct"], "fields_total": a["fields_total"],
                              "wilson": a.get("wilson95"), "items": a["items_fully_correct"], "items_total": a["items"],
                              "given_labels": a["given_allowed_labels"], "reader_counts": a.get("reader_value_counts"), "truncated": a["truncated"],
                              "stop_reasons": a["stop_reasons"], "thinking_total": a.get("thinking_tokens_total", 0), "by_sub_task": a.get("by_sub_task") or {},
                              "latency_ms_median": a.get("latency_ms_median"),
                              "summary_cost_per_1k": a["cost_per_1k_items_usd"]} for a in d["arms"] if a["arm_id"] in CAT1_ARMS}
        levers = [{"lever": lv["lever"], "label": lv["label"], "from": lv["from_arm"], "to": lv["to_arm"], "comparable": lv["comparable_accuracy"],
                   "accuracy_change_pp": lv["accuracy_change_pp"]} for lv in d["levers"]]
        info = {"arms": arms, "levers": levers, "misses": d.get("misses") or [], "data_quality": d.get("data_quality") or {},
                "write_up_note": d.get("write_up_note") or {}, "run_ids": d.get("run_ids") or {}, "deck_profile": d.get("deck_profile") or {},
                "repeats": d.get("repeats"), "items": d.get("items"), "fields_per_arm": d.get("fields_per_arm"), "reader_model": d.get("reader_model"),
                "reader_passes": d.get("reader_passes"), "reader_check_note": d.get("reader_check_note") or "", "settings": d.get("settings") or {}}
        return info, "backend/replays/cat1_ablation_summary.json"
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT1_ABLATION_ANALYSIS.read_text())
        arms = {}
        for a in CAT1_ARMS:
            m = d["arms"][a]
            acc = m.get("accuracy") or {}
            fa = acc.get("field_accuracy") or {}
            arms[a] = {"label": a, "task": next(x["task"] for x in d["design"]["arms"] if x["arm_id"] == a), "runs": m["runs"],
                       "fields": fa.get("hits"), "fields_total": fa.get("total"), "wilson": [x * 100 for x in fa["wilson95"]] if fa.get("wilson95") else None,
                       "items": acc.get("items_fully_correct"), "items_total": acc.get("items", 0), "given_labels": not a.endswith("_report"),
                       "reader_counts": m.get("judge_value_counts"), "truncated": m["truncated"],
                       "stop_reasons": m["stop_reasons"], "thinking_total": None, "by_sub_task": {}, "latency_ms_median": (m.get("latency_ms") or {}).get("median"),
                       "summary_cost_per_1k": m["cost_per_1k_items_usd"]}
        levers = [{"lever": lv["lever"], "label": lv["lever"], "from": lv["from"], "to": lv["to"],
                   "comparable": not (lv["from"].endswith("_report") or lv["to"].endswith("_report")),
                   "accuracy_change_pp": lv["accuracy_change_pp"]} for lv in d["levers"]]
        info = {"arms": arms, "levers": levers, "misses": [], "data_quality": d.get("data_quality") or {}, "write_up_note": {}, "deck_profile": {},
                "run_ids": {}, "repeats": d["design"]["repeats"], "items": len(d["design"]["items"]),
                "fields_per_arm": d["design"]["ground_truth_fields"] * d["design"]["repeats"], "reader_model": d["design"]["judge_model"],
                "reader_passes": d["design"]["judge_passes"], "reader_check_note": "", "settings": {}}
        return info, "analysis/cat1_ablation.json"
    except (OSError, KeyError, TypeError, StopIteration, json.JSONDecodeError):
        return None, "neither backend/replays/cat1_ablation_summary.json nor analysis/cat1_ablation.json could be read"


def cat1_ablation_units(run_ids):
    """One unit per ablation run, selected by run_id (the summary's list) or, without it, the latest ok record per run_id;
    the JSONL is only read. Costs are recomputed from each record's tokens with this script's rate cards."""
    latest = {}
    for line in CAT1_ABLATION.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("status") == "ok":
                latest[r["run_id"]] = r
    ids = run_ids or {a: sorted(i for i, r in latest.items() if r["arm_id"] == a) for a in CAT1_ARMS}
    units = defaultdict(list)
    for arm in CAT1_ARMS:
        for i in ids.get(arm) or []:
            r = latest[i]
            model = r.get("model_returned") if r.get("model_returned") in RATE_CARDS["official"] else CAT1_ARM_MODEL[arm]
            units[arm].append({"item": r["item_id"], "run_id": i, "calls": [call(model, r["input_tokens"], r["output_tokens"])],
                               "stop_reason": r.get("stop_reason"), "hit_max_tokens": r.get("stop_reason") == "max_tokens",
                               "thinking": int(r.get("thinking_tokens") or 0), "sub_task": r.get("sub_task")})
    return units


def cat2_units():
    """(units by app rung: the latest ok experiment draft per draft id; section regenerations by model from
    section_regens.jsonl, see cat2_regens). Both JSONL files are only read."""
    latest = {}
    lines = CAT2_DRAFTS.read_text().splitlines() if CAT2_DRAFTS.is_file() else []
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        rung = CAT2_RUNG_OF.get((r.get("arm"), r.get("model_key")))
        if r.get("status") == "ok" and rung:
            latest[r["draft_id"]] = (rung, r)
    units = defaultdict(list)
    for did in sorted(latest):
        rung, r = latest[did]
        units[rung].append({"item": f"{r['preset_id']}/r{r['repeat_index']}", "preset": r["preset_id"],
                            "calls": [call(r["model_id"], r["input_tokens"], r["output_tokens"], r.get("cache_creation_tokens"), r.get("cache_read_tokens"))],
                            "stop_reason": r.get("stop_reason"), "max_tokens": r.get("max_tokens"),
                            "truncated": bool(r.get("truncated")) or r.get("stop_reason") == "max_tokens"})
    return units, cat2_regens(latest)


def cat2_regens(latest_drafts):
    """Section regenerations by model: the latest ok record per key in section_regens.jsonl that was made on the
    current golden template draft of the same model (base draft id and section content match). Each carries the
    cost of that base draft (its experiment record). Empty until every planned regeneration has a current record."""
    golden = load(2)
    latest = {}
    lines = CAT2_REGENS.read_text().splitlines() if CAT2_REGENS.is_file() else []
    for line in lines:
        if line.strip():
            r = json.loads(line)
            if r.get("status") == "ok":
                latest[r["regen_key"]] = r
    by_id = {r["draft_id"]: r for _, r in latest_drafts.values()}
    regens = defaultdict(list)  # model -> list of {item, section, call, base_call}
    for key in sorted(latest):
        r = latest[key]
        g = (golden.get("presets") or {}).get(r["preset_id"]) or {}
        rung = f"{r['model_key']}_templated"
        sec = ((g.get("rungs") or {}).get(rung) or {}).get("structured_draft", {}).get(r["section_key"])
        base_id = ((g.get("provenance") or {}).get(rung) or {}).get("draft_id")
        sha = hashlib.sha256(json.dumps(sec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        base = by_id.get(base_id)
        if sec is None or r.get("base_draft_id") != base_id or r.get("base_section_sha256") != sha or base is None:
            continue
        regens[r["model_tier"]].append({"item": r["preset_id"], "section": r["section_key"], "truncated": bool(r.get("truncated")),
                                        "call": call(r["model_id"], r["input_tokens"], r["output_tokens"]),
                                        "base_call": call(base["model_id"], base["input_tokens"], base["output_tokens"])})
    if sum(len(v) for v in regens.values()) < CAT2_REGENS_PLANNED:
        return {}
    return dict(regens)


def cat3_rerun_records():
    """Latest ok quality-rerun record per (rung, session, repeat) of the two displayed versions; the JSONL is only
    read. None if absent."""
    try:
        lines = CAT3_RERUN.read_text().splitlines()
    except OSError:
        return None
    latest = {}
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") == "ok" and r.get("rung_id") in CAT3_RUNGS:
            latest[(r["rung_id"], r["preset_id"], int(r["repeat_index"]))] = r
    return [latest[k] for k in sorted(latest)] or None


def _cat3_unit(item, turns):
    """Session-phase calls only: turns 1-10 and the compactions before them (the recall probes are excluded)."""
    calls, per_turn = [], []
    for t in turns:
        comp = t.get("compaction")
        if comp:  # quality-rerun record
            calls.append(call(comp["model_id"], comp["input_tokens"], comp["output_tokens"], comp.get("cache_creation_tokens"), comp.get("cache_read_tokens"), role="compactor"))
        elif t.get("compaction_model_id"):  # golden-replay turn
            calls.append(call(t["compaction_model_id"], t["compaction_input_tokens"], t["compaction_output_tokens"],
                              t.get("compaction_cache_creation_tokens"), t.get("compaction_cache_read_tokens"), role="compactor"))
        c = call(t["model_id"], t["input_tokens"], t["output_tokens"], t["cache_creation_tokens"], t["cache_read_tokens"], role="turn")
        calls.append(c)
        per_turn.append({"turn": t["turn_number"], "prompt": prompt_tokens(c), "output": c["out"], "thinking": int(t.get("thinking_tokens") or 0),
                         "stop_reason": t.get("stop_reason")})
    return {"item": item, "calls": calls, "per_turn": per_turn}


def cat3_units():
    """(units by rung, source label, thinking/stop-reason stats over every call in the records)."""
    recs = cat3_rerun_records()
    units = defaultdict(list)
    if recs is None:
        for sid, p in load(3)["presets"].items():
            for rung, turns in p["rungs"].items():
                units[rung].append(_cat3_unit(sid, turns))
        return units, "golden replays", None
    calls = []
    for r in recs:
        units[r["rung_id"]].append(_cat3_unit(f"{r['preset_id']}/r{r['repeat_index']}", r["turns"]))
        calls += [("turn", t) for t in r["turns"]] + [("compaction", t["compaction"]) for t in r["turns"] if t.get("compaction")]
        calls += [("probe", p) for p in r.get("probes") or []] + ([("compaction", r["probe_compaction"])] if r.get("probe_compaction") else [])
    tp = [c for kind, c in calls if kind in ("turn", "probe")]
    stats = {
        "records": len(recs),
        "turn_and_probe_calls": len(tp),
        "turn_and_probe_calls_with_thinking": sum(1 for c in tp if int(c.get("thinking_tokens") or 0) > 0),
        "max_thinking_tokens": max(int(c.get("thinking_tokens") or 0) for _, c in calls),
        "compaction_calls": sum(1 for kind, _ in calls if kind == "compaction"),
        "compaction_calls_with_thinking": sum(1 for kind, c in calls if kind == "compaction" and int(c.get("thinking_tokens") or 0) > 0),
        "stop_reasons": dict(sorted(Counter(str(c.get("stop_reason")) for _, c in calls).items())),
    }
    return units, "quality rerun", stats


def _measure(m):
    """{hits,total,rate,ci_low,ci_high} from the app summary or the analysis JSON's {hits,total,rate,wilson95}."""
    if not m:
        return None
    lo, hi = m.get("ci_low"), m.get("ci_high")
    if lo is None and m.get("wilson95"):
        lo, hi = m["wilson95"]
    return {"hits": m["hits"], "total": m["total"], "rate": m.get("rate"), "ci_low": lo, "ci_high": hi}


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes in n trials; (None, None) when n == 0."""
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), min(1.0, c + h)


def cat2_quality():
    """Per-cell quality from the app summary: ({"cells": rung -> cell, "h2h": head_to_head, "counts": counts}, source info)
    or (None, reason)."""
    try:
        d = json.loads(CAT2_QUALITY_SUMMARY.read_text())
        cells = {c["rung_id"]: c for c in d["cells"]}
        return {"cells": cells, "h2h": d["head_to_head"], "counts": d["counts"]}, {
            "file": "backend/replays/cat2_quality_summary.json", "keys_version": d.get("keys_version"), "judge_model": d["judge_model"],
            "passes": d["passes_per_draft"], "drafts_per_cell": d["drafts_per_cell"], "documents": list(d["documents"]),
            "max_tokens": d.get("max_tokens") or {}}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, {"file": None, "reason": "backend/replays/cat2_quality_summary.json could not be read"}


def _c2_frac(m):
    return f"{m['hits']}/{m['total']}" if m else "—"


def _c2_h2h(b):
    """'template W – unbounded W – ties T' for one head-to-head block."""
    o = b["overall"]
    return f"template {o['template_wins']} – unbounded {o['unbounded_wins']} – ties {o['ties']} ({b['calls']} calls)"


def cat3_quality():
    """Per-rung answer-key scores: (rung -> measures, source file label) or (None, reason)."""
    try:
        d = json.loads(CAT3_QUALITY_SUMMARY.read_text())
        rungs = {r["rung_id"]: {"runs": r["runs"], "turn_recall": _measure(r["turn_recall"]), "ledger_recall": _measure(r["ledger_recall"]),
                                "ledger_by_origin": {k: _measure(v) for k, v in (r.get("ledger_by_origin") or {}).items()},
                                "probe_accuracy": _measure(r["probe_accuracy"])} for r in d["rungs"] if r["rung_id"] in CAT3_RUNGS}
        return rungs, {"file": "backend/replays/cat3_quality_summary.json", "keys_version": d.get("keys_version"), "runs": d.get("runs")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT3_QUALITY_ANALYSIS.read_text())
        rungs = {}
        for rid, v in d["rerun"]["rungs"].items():
            if rid not in CAT3_RUNGS:
                continue
            q = v["quality"]
            rungs[rid] = {"runs": q.get("sessions") or v["cost"]["runs"], "turn_recall": _measure(q["turn_recall"]["turns_1_9"]),
                          "ledger_recall": _measure(q["ledger_recall"]["overall"]),
                          "ledger_by_origin": {k.replace("origin_", "").replace("_", "-"): _measure(m) for k, m in (q["ledger_recall"].get("by_origin") or {}).items()},
                          "probe_accuracy": _measure(q["probe_accuracy"]["overall"])}
        return rungs, {"file": "analysis/cat3_quality_rerun.json", "keys_version": d.get("keys_version"), "runs": d["rerun"].get("ok_runs_used")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, {"file": None, "reason": "neither backend/replays/cat3_quality_summary.json nor analysis/cat3_quality_rerun.json could be read"}


def cat4_rerun_records():
    """Latest ok quality-rerun record per (rung, scale, repeat) of the two displayed versions, at the current
    synthesis cap and in the version's answer format. None if absent."""
    try:
        lines = CAT4_RERUN.read_text().splitlines()
    except OSError:
        return None
    latest = {}
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        st = r.get("settings") or {}
        rung = r.get("rung_id")
        if (r.get("status") == "ok" and rung in CAT4_RUNGS and st.get("synth_max_tokens") == CAT4_SYNTH_MAX_TOKENS
                and (st.get("answer_format") or "full_corpus") == CAT4_ANSWER_FORMAT[rung]):
            latest[(rung, int(r["scale"]), int(r["repeat_index"]))] = r
    return [latest[k] for k in sorted(latest)] or None


def _cat4_key(rung, scale):
    return f"{rung}|{scale}"


def cat4_units():
    """(units keyed 'rung|scale', source label, call stats). One unit = one 4-question audit; each rerun session
    (8 questions) is split into its two audits. Falls back to the golden replays (scale 1) without the rerun."""
    recs = cat4_rerun_records()
    units = defaultdict(list)
    if recs is None:
        for aid, p in load(4)["presets"].items():
            for rung, qs in p["rungs"].items():
                if rung not in CAT4_RUNGS:
                    continue
                calls, per_q = [], []
                for q in qs:
                    qc = []
                    if q.get("reranker_model_id"):
                        qc.append(call(q["reranker_model_id"], q["reranker_input_tokens"], q["reranker_output_tokens"],
                                       q.get("reranker_cache_creation_tokens"), q.get("reranker_cache_read_tokens"), role="rerank"))
                    qc.append(call(q["model_id"], q["input_tokens"], q["output_tokens"], q["cache_creation_tokens"], q["cache_read_tokens"], role="synthesis"))
                    calls += qc
                    per_q.append({"q": q["question_id"], "calls": qc, "citations": len(q.get("citations") or []),
                                  "stop_reason": q.get("stop_reason"), "thinking": int(q.get("thinking_tokens") or 0)})
                units[_cat4_key(rung, 1)].append({"item": aid, "calls": calls, "per_question": per_q})
        return units, "golden replays", None
    synth = []
    for r in recs:
        for pid in sorted({a["preset_id"] for a in r["answers"]}):
            calls, per_q = [], []
            for a in (x for x in r["answers"] if x["preset_id"] == pid):
                qc = [call(c["model_id"], c["input_tokens"], c["output_tokens"], c.get("cache_creation_tokens"), c.get("cache_read_tokens"), role=c["role"])
                      for c in a["calls"]]
                s_call = next(c for c in a["calls"] if c["role"] == "synthesis")
                synth.append(s_call)
                calls += qc
                per_q.append({"q": a["question_id"], "calls": qc, "citations": len(a.get("citations") or []),
                              "stop_reason": s_call.get("stop_reason"), "thinking": int(s_call.get("thinking_tokens") or 0)})
            units[_cat4_key(r["rung_id"], int(r["scale"]))].append({"item": f"{pid}/s{r['scale']}/r{r['repeat_index']}", "calls": calls, "per_question": per_q})
    stats = {
        "records": len(recs),
        "answers": len(synth),
        "synthesis_stop_reasons": dict(sorted(Counter(str(c.get("stop_reason")) for c in synth).items())),
        "synthesis_outputs_above_app_cap_before": sum(1 for c in synth if int(c["output_tokens"]) > CAT4_APP_MAX_TOKENS_BEFORE),
        "synthesis_calls_with_thinking": sum(1 for c in synth if int(c.get("thinking_tokens") or 0) > 0),
        "max_synthesis_output": max(int(c["output_tokens"]) for c in synth),
    }
    return units, "quality rerun", stats


_CAT4_CELL_FIELDS = ("answers", "fact_recall", "fact_recall_supplier_specific", "citations_per_answer_mean", "zero_citation_answers",
                     "expected_chunk_recall", "citations_at_expected", "cited_support", "contaminated_answers",
                     "value_contaminated_unattributed_answers", "exposure_answers", "recall_after_rerank",
                     "distractors_selected", "judged", "correctness_mean", "completeness_mean", "material_errors",
                     "answers_with_material_error")


def cat4_quality():
    """(cells keyed 'rung|scale' for the two displayed versions, source) or (None, reason)."""
    try:
        d = json.loads(CAT4_QUALITY_SUMMARY.read_text())
        cells = {_cat4_key(c["rung_id"], c["scale"]): {k: c.get(k) for k in _CAT4_CELL_FIELDS}
                 for c in d["cells"] if c["rung_id"] in CAT4_RUNGS}
        return cells, {"file": "backend/replays/cat4_quality_summary.json", "keys_version": d.get("keys_version"),
                       "judge_model": d.get("judge_model"), "judge_passes": d.get("judge_passes"),
                       "answers": sum(c["answers"] for c in cells.values()), "judged": sum(c["judged"] or 0 for c in cells.values()),
                       "sessions_per_cell": d.get("sessions_per_cell"), "corpus": d.get("corpus")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT4_QUALITY_ANALYSIS.read_text())
        cells = {}
        for g in d["rerun"]["groups"].values():
            if g["rung_id"] not in CAT4_RUNGS:
                continue
            ret, j = g.get("retrieval") or {}, g.get("judge") or {}
            cells[_cat4_key(g["rung_id"], g["scale"])] = {
                "answers": g["answers"], "fact_recall": g["fact_recall"], "fact_recall_supplier_specific": g["fact_recall_supplier_specific"],
                "citations_per_answer_mean": g["citations_per_answer_mean"], "zero_citation_answers": g["zero_citation_answers"],
                "expected_chunk_recall": g["expected_chunk_recall"], "citations_at_expected": g["citations_at_expected"],
                "cited_support": g["cited_support"], "contaminated_answers": g["contaminated_answers"],
                "value_contaminated_unattributed_answers": g.get("value_contaminated_unattributed_answers"),
                "exposure_answers": g.get("answers_whose_synthesis_saw_distractor_text"),
                "recall_after_rerank": ret.get("recall_after_rerank"),
                "distractors_selected": ret.get("distractors_selected"), "judged": j.get("judgements") or 0,
                "correctness_mean": j.get("correctness_mean"), "completeness_mean": j.get("completeness_mean"),
                "material_errors": j.get("material_errors"), "answers_with_material_error": j.get("answers_with_material_error"),
            }
        return cells, {"file": "analysis/cat4_quality_rerun.json", "keys_version": d.get("keys_version"), "judge_model": None,
                       "judge_passes": 1, "answers": sum(c["answers"] for c in cells.values()),
                       "judged": sum(c["judged"] for c in cells.values()), "sessions_per_cell": None, "corpus": d.get("corpus")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, {"file": None, "reason": "neither backend/replays/cat4_quality_summary.json nor analysis/cat4_quality_rerun.json could be read"}


def cat5_golden_units(seeds):
    """Fallback: one unit per (invoice x app rung) from the golden replays, quality from the seed traces."""
    d = load(5)
    pat = {"unbounded_sonnet_loop": "unbounded_uncached_react_loop", "bounded_sonnet_cached_gate": "bounded_sonnet_cached_gate",
           "hybrid_haiku_sonnet_governed": "hybrid_haiku_sonnet_governed_loop",
           "unbounded_haiku_loop": "unbounded_uncached_react_loop_haiku"}
    units = defaultdict(list)
    for iid, p in d["presets"].items():
        for rung, r in p["rungs"].items():
            calls = [call(s["model_id"], s["input_tokens"], s["output_tokens"], s["cache_creation_tokens"], s["cache_read_tokens"]) for s in r["steps"]]
            ev = None
            for m in (SONNET, HAIKU):
                s = seeds.get(("cat5_process_orchestration", m, pat[rung], iid))
                if s:
                    ev = s["response"]["structured_output"].get("evaluation")
            units[rung].append({"item": iid, "calls": calls, "steps": len(calls), "tool_calls": r["total_tool_calls"],
                                "optimal_tool_calls": r["optimal_tool_calls"], "escalated": any(c["model"] == SONNET for c in calls) and rung.startswith("hybrid"),
                                "decision": (r.get("committed_voucher") or {}).get("decision"), "evaluation": ev})
    return units


def _cat5_priced_model(t):
    m = t.get("model_id")
    return m if m in RATE_CARDS["official"] else (t.get("intended_model_id") or SONNET)


def cat5_ablation_info():
    """Quality and the record selection for the three cells, from replays/cat5_ablation_summary.json, falling back to
    analysis/cat5_ablation.json. Returns (info, source); info is None when neither file can be read."""
    try:
        d = json.loads(CAT5_ABLATION_SUMMARY.read_text())
        arms = {a["arm_id"]: {
            "label": a["label"], "runs": a["runs"], "exact": a["exact"], "decision_correct": a["decision_correct"],
            "turns_mean": a["turns_mean"], "turns_max": a["turns_max"], "turn_cap": a["turn_cap"], "cap_hits": a["cap_hits"],
            "truncated_turns": a["truncated_turns"], "escalate": a["escalate"], "escalation_fired": a["escalation_fired"],
            "escalation_expected": a["escalation_expected"], "expected_runs": a.get("expected_runs") or a["runs"],
            "pending_runs": a.get("pending_runs", 0), "pending_invoices": a.get("pending_invoices") or [],
            "by_invoice": {p: (v["exact"], v["runs"]) for p, v in (a.get("by_invoice") or {}).items()},
            "summary_cost_billed": a["cost_per_1k_billed_usd"]} for a in d["arms"]}
        info = {"arms": arms, "run_ids": d.get("run_ids"), "data_quality": d.get("data_quality") or {},
                "non_exact_runs": d.get("non_exact_runs") or [], "invoices_pooled": d.get("invoice_count_pooled"),
                "repeats": d.get("repeats"), "settings": d.get("settings") or {}, "fixture_version": d.get("fixture_version")}
        return info, "backend/replays/cat5_ablation_summary.json"
    except (OSError, KeyError, TypeError, IndexError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT5_ABLATION_ANALYSIS.read_text())
        arms = {}
        for a in d["arm_ids"]:
            m, spec = d["arms"][a], d["arms_spec"][a]
            pend = m.get("pending") or {}
            arms[a] = {"label": a, "runs": m["runs"], "exact": m["exact"]["k"], "decision_correct": m["decision_correct"]["k"],
                       "turns_mean": m["turns"]["mean"], "turns_max": m["turns"]["max"], "turn_cap": spec["turn_cap"],
                       "cap_hits": m["cap_hits"], "truncated_turns": m["truncated_turns"], "escalate": spec["escalate"],
                       "escalation_fired": m["escalation"]["fired"], "escalation_expected": m["escalation"]["expected"],
                       "expected_runs": m["runs"] + pend.get("runs", 0), "pending_runs": pend.get("runs", 0),
                       "pending_invoices": pend.get("invoices") or [],
                       "by_invoice": {p: (v["exact"]["k"], v["runs"]) for p, v in (m.get("by_invoice") or {}).items()},
                       "summary_cost_billed": m["cost_per_1k_invoices_usd"]["billed"]}
        info = {"arms": arms, "run_ids": d.get("run_ids"),
                "data_quality": {k: (len(v) if isinstance(v, list) else v) for k, v in (d.get("data_quality") or {}).items()},
                "non_exact_runs": d.get("non_exact_runs") or [], "invoices_pooled": len(d.get("preset_ids") or []),
                "repeats": d.get("expected_repeats"), "settings": d.get("settings") or {}, "fixture_version": d.get("fixture_version")}
        return info, "analysis/cat5_ablation.json"
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, "neither backend/replays/cat5_ablation_summary.json nor analysis/cat5_ablation.json could be read"


def cat5_ablation_units(run_ids):
    """Units for the runs behind the three cells, selected by run_id from runs.jsonl; the JSONL is only read."""
    by_id = {}
    for line in CAT5_ABLATION.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            by_id[r["run_id"]] = r

    def unit(r):
        calls = [call(_cat5_priced_model(t), t["input_tokens"], t["output_tokens"], t.get("cache_creation_tokens"), t.get("cache_read_tokens"))
                 for t in r["turns"]]
        return {"item": f"{r['preset_id']}/r{r['repeat_index']}", "preset_id": r["preset_id"], "calls": calls, "steps": len(calls),
                "cap_hit": bool(r.get("cap_hit")), "escalated": bool(r.get("escalation_fired"))}
    return {a: [unit(by_id[i]) for i in ids] for a, ids in (run_ids.get("pooled") or {}).items()}


def cat6_rerun_records():
    """Latest ok fair-rerun record per (arm, preset, repeat); the JSONL is only read."""
    latest = {}
    for line in CAT6_RERUN.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") == "ok":
            latest[(r["arm_id"], r["preset_id"], int(r["repeat_index"]))] = r
    return [latest[k] for k in sorted(latest)]


def cat6_units():
    units = defaultdict(list)
    for r in cat6_rerun_records():
        calls = [call(t["model_id"], t["input_tokens"], t["output_tokens"], t["cache_creation_tokens"], t["cache_read_tokens"], role=t["agent_role"])
                 for t in r["turns"]]

        def verdict_of(attempt):
            sb = (r.get(attempt) or {}).get("sandbox") or {}
            return {"passed": sb.get("passed_checks"), "checks": sb.get("total_checks"), "verified": bool(sb.get("verified_outcome"))}

        fin, first = verdict_of("final"), verdict_of("first_attempt")
        units[r["arm_id"]].append({
            "item": f"{r['preset_id']}/r{r['repeat_index']}", "calls": calls,
            "verified": fin["verified"], "passed": fin["passed"], "checks": fin["checks"], "first_verified": first["verified"],
            "retries": int(r.get("retries_used") or 0),
            "turns_at_max_tokens": sum(1 for t in r["turns"] if t.get("stop_reason") == "max_tokens"),
            "turn1_prefix": calls[0]["cw"] + calls[0]["cr"],
            "model_ms": sum(int(t.get("latency_ms") or 0) for t in r["turns"]),
        })
    return units


# --------------------------------------------------------------- 3. claim checks
def summarize_rungs(units, order, card="official"):
    out = {}
    for rung in order:
        us = units[rung]
        billed = [unit_cost(u["calls"], card, "billed") for u in us]
        warm = [unit_cost(u["calls"], card, "warm") for u in us]
        cold = [unit_cost(u["calls"], card, "cold") for u in us]
        toks = [tok(u["calls"]) for u in us]
        out[rung] = {
            "n": len(us),
            "cost_per_1k_billed": st.mean(billed) * 1000,
            "cost_per_1k_warm": st.mean(warm) * 1000,
            "cost_per_1k_cold": st.mean(cold) * 1000,
            "cost_per_1k_billed_repo_card": st.mean(unit_cost(u["calls"], "repo", "billed") for u in us) * 1000,
            "prompt_tokens_median": med([t["prompt"] for t in toks]),
            "prompt_tokens_range": rng([t["prompt"] for t in toks]),
            "output_tokens_median": med([t["output"] for t in toks]),
            "output_tokens_range": rng([t["output"] for t in toks]),
            "total_tokens_median": med([t["total"] for t in toks]),
            "io_ratio_median": med([t["prompt"] / t["output"] if t["output"] else None for t in toks]),
            "output_cost_share_median": med([output_cost_share(u["calls"], card) for u in us]),
            "max_call_prompt": max(t["max_call_prompt"] for t in toks),
        }
    return out


def verdict(ok, partial=False):
    return "SUPPORTED" if ok else ("PARTLY SUPPORTED" if partial else "NOT SUPPORTED")


NEUTRAL_NOTE = ("These experiments compare system designs (what is asked for, how much context is sent, caching, tools, routing between model sizes) "
                "in one synthetic lab setup; the results describe those configurations on these tasks and are not an assessment of any model.")


IMPLICIT_RULE = ("Rule for every implicit quality row (Categories 1–6): SUPPORTED only when the cheaper versions are at least equal to the version they "
                 "replace on every quality measure the row reports; PARTLY SUPPORTED when no clear loss is detected (95% Wilson intervals overlap) but a "
                 "point estimate is lower, a ceiling prevents detecting a loss, or a clear loss is confined to a subset the row reports separately; NOT "
                 "SUPPORTED when a loss is clear (the intervals do not overlap, or the head-to-head record is one-sided: the cheaper versions' win-share "
                 "interval lies entirely below 50%).")


def implicit_verdict(clear_loss, at_least_equal, ceiling=False, subset_loss=False):
    """The written rule for the implicit quality rows (IMPLICIT_RULE), applied identically in every category."""
    if clear_loss:
        return "NOT SUPPORTED"
    if at_least_equal and not ceiling and not subset_loss:
        return "SUPPORTED"
    return "PARTLY SUPPORTED"


def analyse():
    seeds = seed_index()
    res = {"dedup": dedup_audit(), "categories": {}, "claims": []}
    claims = res["claims"]

    def claim(cat, text, measured, v, note=""):
        claims.append({"category": cat, "claim": text, "measured": measured, "verdict": v, "note": note})

    # ---------------- Cat 1 (four cells: Sonnet / Haiku x without / with the improvement, 12 items x 3 repeats)
    info1, src1 = cat1_ablation_info()
    u1 = None
    if info1:
        try:
            u1 = cat1_ablation_units(info1["run_ids"])
        except (OSError, KeyError, json.JSONDecodeError):
            u1 = None
    if info1 and u1 and all(u1[a] for a in CAT1_ARMS):
        s1 = summarize_rungs(u1, CAT1_ARMS)
        for a in ("sonnet_schema", "haiku_schema"):
            s1[f"{a}_batch"] = {"cost_per_1k_billed": st.mean(unit_cost(u["calls"], batch=True) for u in u1[a]) * 1000, "computed": True}
        cost1 = {a: s1[a]["cost_per_1k_billed"] for a in CAT1_ARMS}
        levers1 = []
        for lv in info1["levers"]:
            if lv["from"] in cost1 and lv["to"] in cost1:
                levers1.append({**lv, "cost_from": cost1[lv["from"]], "cost_to": cost1[lv["to"]],
                                "cost_change_pct": (cost1[lv["to"]] / cost1[lv["from"]] - 1) * 100 if cost1[lv["from"]] else None,
                                "fields_from": info1["arms"][lv["from"]]["fields"], "fields_to": info1["arms"][lv["to"]]["fields"],
                                "fields_total": info1["arms"][lv["to"]]["fields_total"]})
        lv1 = {lv["lever"]: lv for lv in levers1}
        q1 = info1["arms"]
        records1 = sum(len(u1[a]) for a in CAT1_ARMS)
        res["categories"]["cat1"] = {
            "source": "ablation", "summary_source": src1, "rungs": s1, "quality": q1, "levers": levers1, "records": records1,
            "n_items": info1["items"], "repeats": info1["repeats"], "fields_per_arm": info1["fields_per_arm"],
            "misses": info1["misses"], "write_up_note": info1["write_up_note"], "data_quality": info1["data_quality"],
            "reader_model": info1["reader_model"], "reader_passes": info1["reader_passes"], "reader_check_note": info1["reader_check_note"],
            "settings": info1["settings"],
            "truncated_runs": {a: sum(1 for u in u1[a] if u["hit_max_tokens"]) for a in CAT1_ARMS},
            "thinking_tokens_total": {a: sum(u["thinking"] for u in u1[a]) for a in CAT1_ARMS},
            "max_cost_diff_vs_summary_per_1k": max(abs(cost1[a] - (q1[a]["summary_cost_per_1k"] or 0)) for a in CAT1_ARMS),
        }
        hs, ss = s1["haiku_schema"], s1["sonnet_schema"]
        wr = s1["sonnet_report"]
        dp = info1.get("deck_profile") or {}
        band_rule = " Band rule: SUPPORTED when the whole range is in the band, PARTLY when the median is, NOT SUPPORTED otherwise."

        def in_band(lo, hi, x):
            return lo <= x <= hi

        sp_lo, sp_hi = hs["prompt_tokens_range"]
        wp_lo, wp_hi = wr["prompt_tokens_range"]
        pay = (f"; payload alone ≈{dp['payload_tokens_min']:,.0f}–{dp['payload_tokens_max']:,.0f} (median {dp['payload_tokens_median']:,.0f}; "
               "estimated from a linear fit of the write-up runs' input tokens on payload length)") if dp.get("payload_tokens_median") else ""
        claim("Cat 1", "Input 500–1,500 tokens",
              f"prompt sent with the improvement (schema) {sp_lo:,}–{sp_hi:,} (median {hs['prompt_tokens_median']:,.0f}); without (write-up) {wp_lo:,}–{wp_hi:,} "
              f"(median {wr['prompt_tokens_median']:,.0f}){pay} (n={hs['n']} runs per cell)",
              verdict(500 <= sp_lo and sp_hi <= 1500 and 500 <= wp_lo and wp_hi <= 1500,
                      in_band(500, 1500, hs["prompt_tokens_median"]) and in_band(500, 1500, wr["prompt_tokens_median"])),
              "Both medians are in the band; the ranges spill on both sides: the six batch items are short (write-up prompts from "
              f"{wp_lo:,} tokens), and the system prompt plus the JSON schema add ~600 tokens, so the longest schema prompts reach {sp_hi:,}." + band_rule)
        o_lo, o_hi = hs["output_tokens_range"]
        claim("Cat 1", "Output 10–100 tokens",
              f"with the improvement: Haiku {o_lo}–{o_hi} (median {hs['output_tokens_median']:.0f}), Sonnet {ss['output_tokens_range'][0]}–{ss['output_tokens_range'][1]} "
              f"(median {ss['output_tokens_median']:.0f}); without: write-ups {min(s1['haiku_report']['output_tokens_range'][0], wr['output_tokens_range'][0]):,}–"
              f"{max(s1['haiku_report']['output_tokens_range'][1], wr['output_tokens_range'][1]):,} (n={hs['n']} runs per cell)",
              verdict(10 <= o_lo and o_hi <= 100 and 10 <= ss["output_tokens_range"][0] and ss["output_tokens_range"][1] <= 100,
                      hs["output_tokens_median"] <= 100 and ss["output_tokens_median"] <= 100),
              "The medians are inside the band and the longest classification answers run just over it." + band_rule)
        claim("Cat 1", "Input:output ≈ 20:1 to 50:1", f"with the improvement: Haiku median {hs['io_ratio_median']:.0f}:1, Sonnet {ss['io_ratio_median']:.0f}:1; "
              f"without: {wr['io_ratio_median']:.2f}:1 (Sonnet write-up)",
              verdict(20 <= hs["io_ratio_median"] <= 50, hs["io_ratio_median"] > 1),
              "Input-heavy as claimed, but below the 20:1 floor because the classification answer is ~100 tokens and the prompt carries the schema.")
        whole = lv1["whole stack: Sonnet write-up → Haiku schema"]["cost_change_pct"]
        ws_s, ws_h = lv1["write-up → schema (sonnet)"]["cost_change_pct"], lv1["write-up → schema (haiku)"]["cost_change_pct"]
        swap = lv1["Sonnet → Haiku (schema)"]["cost_change_pct"]
        batch_h = s1["haiku_schema_batch"]["cost_per_1k_billed"]
        sav = -whole
        cells = "; ".join(f"{CAT1_ROWS[rk].split(':')[0].lower()} / {CAT1_COLS[ck]} {_money(cost1[a])}/1k" for (rk, ck), a in CAT1_DESIGN.items())
        claim("Cat 1", "Small model + strict JSON schema + batching cuts unit cost by >80%",
              f"Sonnet write-up → Haiku schema {whole:+.1f}% (Batch API price of the Haiku schema version: {_money(batch_h)}/1k, computed, not run). "
              f"The four cells: {cells}. Write-up → schema on the same model {ws_s:+.1f}% (Sonnet) / {ws_h:+.1f}% (Haiku); Sonnet → Haiku with the schema {swap:+.1f}%",
              verdict(whole < -80),
              f"The cut clears 80% before any batch discount; each step clears it on its own (write-up → schema on either model, and Sonnet → Haiku). "
              f"Batching was priced at 50%, not run. No write-up reached its 8,192-token cap ({sum(1 for a in CAT1_ARMS for u in u1[a] if u['hit_max_tokens'])} of {records1} runs truncated).")
        a_s, a_h = q1["sonnet_schema"], q1["haiku_schema"]
        w_s, w_h = q1["sonnet_report"], q1["haiku_report"]
        hi_h, lo_s = (a_h["wilson"] or [0, 0])[1], (a_s["wilson"] or [0, 0])[0]
        it_h, it_s = wilson(a_h["items"], a_h["items_total"]), wilson(a_s["items"], a_s["items_total"])
        clear_hs = hi_h < lo_s or (it_h[1] is not None and it_s[0] is not None and it_h[1] < it_s[0])
        equal_hs = a_h["fields"] >= a_s["fields"] and a_h["items"] >= a_s["items"]
        with_ge = all(q1[w]["fields"] >= q1[o]["fields"] and q1[w]["items"] >= q1[o]["items"]
                      for w, o in (("sonnet_schema", "sonnet_report"), ("haiku_schema", "haiku_report")))
        loss = (a_s["fields"] - a_h["fields"]) / a_h["fields_total"] * 100
        misses_h = sorted({m["item_id"] for m in info1["misses"] if m["arm_id"] == "haiku_schema"})
        claim("Cat 1", "…without losing accuracy (implicit)",
              f"fields correct of {a_s['fields_total']} (items fully correct of {a_s['items_total']}). With vs without, same model: Sonnet {a_s['fields']} ({a_s['items']}) vs "
              f"{w_s['fields']} ({w_s['items']}); Haiku {a_h['fields']} ({a_h['items']}) vs {w_h['fields']} ({w_h['items']}). With the improvement, Haiku vs Sonnet: "
              f"{a_h['fields']} ({a_h['wilson'][0]:.0f}–{a_h['wilson'][1]:.0f}%) vs {a_s['fields']} ({a_s['wilson'][0]:.0f}–{a_s['wilson'][1]:.0f}%), items {a_h['items']} vs {a_s['items']}",
              implicit_verdict(clear_hs, with_ge and equal_hs),
              ("With the improvement every field and item count is at least the write-up's on the same model. " if with_ge else "")
              + "The write-up prompt never lists the allowed labels, so a write-up's score counts the fields where one allowed label can be read off it "
              f"(usable as a classification), read by a blind reader model (`{info1['reader_model']}`, one pass). On the \"with\" row the Haiku version matched "
              f"{a_s['fields'] - a_h['fields']} fewer of {a_h['fields_total']} fields than the Sonnet version (−{loss:.1f} points), all on {len(misses_h)} "
              f"ticket{'s' if len(misses_h) != 1 else ''} ({', '.join(misses_h)}); the 95% Wilson intervals overlap. "
              + ("Implicit-row rule: a clear loss (the intervals do not overlap)." if clear_hs else
                 "Implicit-row rule: equal or better on fields and items." if (with_ge and equal_hs) else
                 "Implicit-row rule: no clear loss is detected (the intervals overlap), but the Haiku point estimates are lower and 36 runs cannot exclude a loss."))
    else:
        reason1 = src1 if not info1 else "the ablation records could not be read"
        res["categories"]["cat1"] = {"source": "unavailable", "reason": reason1, "rungs": {}}
        for c_ in ("Input 500–1,500 tokens", "Output 10–100 tokens", "Input:output ≈ 20:1 to 50:1",
                   "Small model + strict JSON schema + batching cuts unit cost by >80%", "…without losing accuracy (implicit)"):
            claim("Cat 1", c_, "no ablation data", "NOT TESTABLE", reason1)

    # ---------------- Cat 2 (four cells: Sonnet / Haiku x without / with the section template, 4 documents x 3 repeats)
    u2, regens = cat2_units()
    s2 = summarize_rungs(u2, [r for r in CAT2_ORDER if u2.get(r)])
    reg = {m: {"n": len(v), "cost_per_1k": st.mean(call_cost(x["call"]) for x in v) * 1000,
               "base_draft_cost_per_1k": st.mean(call_cost(x["base_call"]) for x in v) * 1000,
               "base_drafts": len({x["item"] for x in v}), "truncated": sum(x["truncated"] for x in v),
               "output_median": med([x["call"]["out"] for x in v]), "input_median": med([x["call"]["in"] for x in v])} for m, v in regens.items()}
    q2, q2_source = cat2_quality()
    qc2 = (q2 or {}).get("cells") or {}
    planned2 = (q2 or {}).get("counts", {}).get("drafts_planned", 48)
    per_cell2 = q2_source.get("drafts_per_cell", 12) if q2 else 12
    docs2 = q2_source.get("documents") if q2 else sorted({u["preset"] for us in u2.values() for u in us})
    diffs2 = [abs(s2[r]["cost_per_1k_billed"] - qc2[r]["cost_per_1k_docs_usd"]) for r in s2 if qc2.get(r, {}).get("cost_per_1k_docs_usd") is not None]
    WS, WH, TS, TH = CAT2_ORDER
    have_wo2, have_wi2 = WS in s2 and WH in s2, TS in s2 and TH in s2
    h2h2 = (q2 or {}).get("h2h") or {}
    res["categories"]["cat2"] = {
        "rungs": s2, "pending_rungs": [r for r in CAT2_ORDER if r not in s2], "records": sum(len(u2[r]) for r in s2), "planned": planned2,
        "drafts_per_cell": per_cell2, "documents": docs2, "truncated": {r: sum(1 for u in u2[r] if u["truncated"]) for r in s2},
        "max_tokens": {r: sorted({u["max_tokens"] for u in u2[r]}) for r in s2},
        "max_cost_diff_vs_summary_per_1k": max(diffs2) if diffs2 else None,
        "draft_count_mismatch_vs_summary": [r for r in s2 if qc2.get(r) and qc2[r].get("drafts") != s2[r]["n"]],
        "section_regen": reg, "section_regen_planned": CAT2_REGENS_PLANNED,
        "quality": q2, "quality_source": q2_source,
    }
    pend2 = (f"Run pending: the unbounded drafts ({sum(1 for r in (WS, WH) if r not in s2) * per_cell2} planned) have not been made yet. ")
    all4 = have_wo2 and have_wi2
    band_rule2 = (" Band rule (all four cells): SUPPORTED when every cell's whole range is in the band, PARTLY when at least one cell's median is, "
                  "NOT SUPPORTED otherwise; NOT TESTABLE while a cell is pending.")

    def rows2(key):
        return "; ".join(f"{CAT2_SHORT[r]} {s2[r][key][0]:,}–{s2[r][key][1]:,} (median {s2[r][key.replace('_range', '_median')]:,.0f})" for r in CAT2_ORDER if r in s2) or "no drafts"

    if all4:
        in_all = all(1500 <= s2[r]["prompt_tokens_range"][0] and s2[r]["prompt_tokens_range"][1] <= 4000 for r in s2)
        in_med = any(1500 <= s2[r]["prompt_tokens_median"] <= 4000 for r in s2)
        add = s2[TS]["prompt_tokens_median"] - s2[WS]["prompt_tokens_median"]
        claim("Cat 2", "Input 1,500–4,000 tokens", f"prompt tokens: {rows2('prompt_tokens_range')}", verdict(in_all, in_med),
              f"The section template and JSON schema add about {add:,.0f} prompt tokens (median, Sonnet)." + band_rule2)
    else:
        claim("Cat 2", "Input 1,500–4,000 tokens", f"prompt tokens: {rows2('prompt_tokens_range')}", "NOT TESTABLE",
              pend2 + "With the template the prompt also carries the section template and the JSON schema." + band_rule2)
    if all4:
        o_all = all(s2[r]["output_tokens_range"][0] >= 800 for r in s2)
        o_med = any(s2[r]["output_tokens_median"] >= 800 for r in s2)
        claim("Cat 2", "Output 800–3,000+ tokens", f"output tokens: {rows2('output_tokens_range')}", verdict(o_all, o_med),
              "The band is open at the top (3,000+), so only the 800 floor is tested." + band_rule2)
    else:
        claim("Cat 2", "Output 800–3,000+ tokens", f"output tokens: {rows2('output_tokens_range')}", "NOT TESTABLE",
              pend2 + "The band is open at the top (3,000+), so only the 800 floor is tested." + band_rule2)
    io_txt = "; ".join(f"{CAT2_SHORT[r]} in:out ≈ {s2[r]['io_ratio_median']:.2f}:1, output {s2[r]['output_cost_share_median'] * 100:.0f}% of cost" for r in CAT2_ORDER if r in s2)
    if all4:
        ratio_ok = all(0.5 <= s2[r]["io_ratio_median"] <= 1.0 for r in s2)
        out_dom = all(s2[r]["output_cost_share_median"] > 0.5 for r in s2)
        claim("Cat 2", "Input:output ≈ 1:1 to 1:2 and output-dominated cost", io_txt, verdict(ratio_ok and out_dom, out_dom),
              "SUPPORTED when every cell's median ratio is 1:1 to 1:2 and output is more than half the cost; PARTLY when only the cost is output-dominated.")
    else:
        claim("Cat 2", "Input:output ≈ 1:1 to 1:2 and output-dominated cost", io_txt or "no drafts", "NOT TESTABLE",
              pend2 + "SUPPORTED when every cell's median ratio is 1:1 to 1:2 and output is more than half the cost; PARTLY when only the cost is output-dominated.")
    claim("Cat 2", "Output tokens cost 3–5× input", "Sonnet 5.5 and Haiku 5.5 output is exactly 5× input", verdict(True))

    regen_txt = _cat2_regen_sentence(reg)
    sv2s = sv2h = None
    if all4:
        sv2s = pct_saving(s2[WS]["cost_per_1k_billed"], s2[TS]["cost_per_1k_billed"])
        sv2h = pct_saving(s2[WH]["cost_per_1k_billed"], s2[TH]["cost_per_1k_billed"])
        out_cut = all(s2[t]["output_tokens_median"] < s2[w]["output_tokens_median"] for w, t in ((WS, TS), (WH, TH)))
        claim("Cat 2", "Section templates + length bounds control output cost",
              f"with vs without on the same model: Sonnet −{sv2s:.0f}% ({_money(s2[WS]['cost_per_1k_billed'])} → {_money(s2[TS]['cost_per_1k_billed'])}/1k), "
              f"Haiku −{sv2h:.0f}% ({_money(s2[WH]['cost_per_1k_billed'])} → {_money(s2[TH]['cost_per_1k_billed'])}/1k); median output "
              f"{s2[WS]['output_tokens_median']:,.0f} → {s2[TS]['output_tokens_median']:,.0f} (Sonnet), {s2[WH]['output_tokens_median']:,.0f} → {s2[TH]['output_tokens_median']:,.0f} (Haiku)"
              + (f"; {regen_txt}" if regen_txt else ""),
              verdict(sv2s > 0 and sv2h > 0 and out_cut, sv2s > 0 or sv2h > 0),
              "SUPPORTED when the template lowers cost and median output on both models. Quality is tested in the next row.")
    else:
        claim("Cat 2", "Section templates + length bounds control output cost",
              (f"with the template: {_money(s2[TS]['cost_per_1k_billed'])} (Sonnet) / {_money(s2[TH]['cost_per_1k_billed'])} (Haiku) per 1k, median output "
               f"{s2[TS]['output_tokens_median']:,.0f} / {s2[TH]['output_tokens_median']:,.0f}" if have_wi2 else "no template drafts")
              + (f"; {regen_txt}" if regen_txt else ""), "NOT TESTABLE", pend2 + "The claim needs the without row on the same model.")

    # implicit quality row: with vs without on the same model; Haiku vs Sonnet on the with row
    def wil(m):
        return wilson(m["hits"], m["total"]) if m else (None, None)

    def lower_clear(cheap, ref):  # cheaper version's 95% interval entirely below the reference's
        a_, b_ = wil(cheap), wil(ref)
        return a_[1] is not None and b_[0] is not None and a_[1] < b_[0]

    def ge_all(cheap, ref):
        return (all(cheap["rubric"][k] >= ref["rubric"][k] for k in CAT2_DIMS) and cheap["serious_per_draft"] <= ref["serious_per_draft"]
                and all(cheap[f]["hits"] / cheap[f]["total"] >= ref[f]["hits"] / ref[f]["total"] for f in ("core_facts", "detail_facts")))

    def qtxt(c):
        r = c["rubric"]
        return (f"accuracy {r['factual_accuracy']:.2f}, coverage {r['coverage']:.2f}, actionability {r['actionability']:.2f}; serious errors "
                f"{c['serious_per_draft']:.2f}/draft; core facts {_c2_frac(c['core_facts'])}, detail facts {_c2_frac(c['detail_facts'])}")

    graded = lambda r: bool(qc2.get(r) and qc2[r].get("status") == "ok" and qc2[r].get("judged_drafts") == qc2[r].get("drafts") and qc2[r].get("rubric"))  # noqa: E731
    hs_txt, hs_loss, hs_ge = "", False, False
    if graded(TS) and graded(TH):
        a_, b_ = qc2[TH], qc2[TS]
        hs_loss = lower_clear(a_["core_facts"], b_["core_facts"]) or lower_clear(a_["detail_facts"], b_["detail_facts"])
        hs_ge = ge_all(a_, b_)
        hs_txt = f"With the template, Haiku vs Sonnet: {qtxt(a_)} vs {qtxt(b_)}"
    if q2 and all4 and all(graded(r) for r in CAT2_ORDER) and h2h2.get("status") == "ok" and h2h2.get("all"):
        hb = h2h2["all"]["overall"]
        dec = hb["template_wins"] + hb["unbounded_wins"]
        lo, hi = wilson(hb["template_wins"], dec)
        pref_loss = hi is not None and hi < 0.5
        same = [(qc2[t], qc2[w]) for w, t in ((WS, TS), (WH, TH))]
        fact_loss = any(lower_clear(c[f], r[f]) for c, r in same for f in ("core_facts", "detail_facts"))
        losses = ((["the head-to-head record is one-sided against the template"] if pref_loss else [])
                  + [f"{f.replace('_', ' ')}, {m} with vs without" for (c, r), m in zip(same, ("Sonnet", "Haiku"))
                     for f in ("core_facts", "detail_facts") if lower_clear(c[f], r[f])]
                  + (["fact intervals, Haiku vs Sonnet with the template"] if hs_loss else []))
        rule_txt = (f" Implicit-row rule: a clear loss ({'; '.join(losses)})." if losses else
                    " Implicit-row rule: equal or better on every measure." if ge else
                    " Implicit-row rule: no clear loss is detected (the intervals overlap), but some point estimates are lower.")
        ge = all(ge_all(c, r) for c, r in same) and hb["template_wins"] >= hb["unbounded_wins"] and hs_ge
        pc = h2h2["all"].get("position_consistency") or {}
        claim("Cat 2", "…without losing draft quality (implicit)",
              f"head-to-head, template vs unbounded on the same document, model and repeat: {_c2_h2h(h2h2['all'])}; template share of decisive comparisons "
              + (f"{lo * 100:.0f}–{hi * 100:.0f}% (95% Wilson). " if lo is not None else "n/a. ")
              + f"Sonnet with vs without: {qtxt(qc2[TS])} vs {qtxt(qc2[WS])}. Haiku with vs without: {qtxt(qc2[TH])} vs {qtxt(qc2[WH])}. {hs_txt}",
              implicit_verdict(pref_loss or fact_loss or hs_loss, ge),
              f"Blind judge (`{q2_source['judge_model']}`, not one of the models under test; {q2_source['passes']} rubric pass per draft; each pair shown in both orders, "
              f"position-consistent in {pc.get('consistent', 0)}/{pc.get('pairs', 0)} pairs); {per_cell2} drafts per cell over {len(docs2)} documents; key facts from a fixed answer key. "
              "Compared under the written rule: the template against the unbounded draft on the same model, and Haiku against Sonnet on the row with the template; "
              "ties are left out of the head-to-head share." + rule_txt)
    else:
        why = pend2 if not all4 else ("Grading or the head-to-head judgements are pending. " if q2 else f"No quality data: {q2_source.get('reason')}. ")
        claim("Cat 2", "…without losing draft quality (implicit)", hs_txt or "no quality data", "NOT TESTABLE",
              why + f"The with-vs-without comparison needs the unbounded drafts graded and {(q2 or {}).get('counts', {}).get('pairwise_planned', 48)} head-to-head judge calls. "
              + ("On the row with the template, Haiku vs Sonnet under the written rule: "
                 + ("a clear loss (fact intervals do not overlap)." if hs_loss else "equal or better on every measure." if hs_ge else
                    "no clear loss (the fact intervals overlap), but some point estimates are lower.") if hs_txt else ""))

    c1 = res["categories"]["cat1"]
    vals_t, parts_t = [], []
    if c1.get("source") == "ablation":
        l1 = {lv["lever"]: lv["cost_change_pct"] for lv in c1["levers"]}
        whole1 = -l1["whole stack: Sonnet write-up → Haiku schema"]
        vals_t.append(whole1)
        parts_t.append(f"Cat 1 −{whole1:.0f}% (Sonnet write-up → Haiku schema; write-up → schema on the same model −{-l1['write-up → schema (sonnet)']:.0f}% (Sonnet) / "
                       f"−{-l1['write-up → schema (haiku)']:.0f}% (Haiku), Sonnet → Haiku with the schema −{-l1['Sonnet → Haiku (schema)']:.0f}%)")
    else:
        parts_t.append("Cat 1 not available")
    if all4:
        vals_t += [sv2s, sv2h]
        parts_t.append(f"Cat 2 −{sv2s:.0f}% (Sonnet) / −{sv2h:.0f}% (Haiku), section template vs unbounded draft on the same model")
    else:
        parts_t.append("Cat 2 section template vs unbounded draft: run pending")
    in_rng = [60 <= v <= 80 for v in vals_t]
    claim("Tiers 1–2 rule", "60–80% lower unit inference cost (Cat 1 & 2)", "; ".join(parts_t),
          verdict(bool(vals_t) and all(in_rng) and all4, any(v > 0 for v in vals_t)) if vals_t else "NOT TESTABLE",
          "SUPPORTED when every measured saving is within 60–80%; PARTLY when the costs fall but a saving lies outside the range"
          + (" or Category 2 is pending" if not all4 else "") + ". "
          + (f"Outside the range: {', '.join(f'{v:.0f}%' for v, ok in zip(vals_t, in_rng) if not ok)}." if not all(in_rng) else ""))

    # ---------------- Cat 3 (quality rerun: without / with the deck's improvement x 2 sessions x 3 repeats)
    u3, cat3_source, cat3_stats = cat3_units()
    order3 = list(CAT3_RUNGS)
    WO3, WI3 = order3  # without (full history, no cache); with (cached prefix + sliding-window summaries)
    s3 = summarize_rungs(u3, order3)
    growth = {}
    for r in order3:
        sl, peak, t1, t3, t6, t10, out_t = [], [], [], [], [], [], []
        for u in u3[r]:
            pt = u["per_turn"]
            sl.append(slope([x["turn"] for x in pt], [x["prompt"] for x in pt]))
            peak.append(max(x["prompt"] for x in pt))
            by = {x["turn"]: x["prompt"] for x in pt}
            t1.append(by[1]); t3.append(by[3]); t6.append(by[6]); t10.append(by[10])
            out_t += [x["output"] for x in pt]
        growth[r] = {"slope_tokens_per_turn": st.mean(sl), "turn1": st.mean(t1), "turn3": st.mean(t3), "turn6": st.mean(t6), "turn10": st.mean(t10),
                     "peak_context": max(peak), "output_per_turn_range": rng(out_t), "output_per_turn_median": med(out_t),
                     "compactor_calls": sum(1 for u in u3[r] for c in u["calls"] if c["role"] == "compactor"),
                     "compactor_calls_per_session": st.mean(sum(1 for c in u["calls"] if c["role"] == "compactor") for u in u3[r])}
    q3, q3_source = cat3_quality()
    all_turns3 = [x for r in order3 for u in u3[r] for x in u["per_turn"]]
    in_band = sum(1 for x in all_turns3 if 150 <= x["output"] <= 600)
    with_thinking = [x for x in all_turns3 if x["thinking"] > 0]
    # the handbook prefix: the cached first turn of the "with" version (cache write + read)
    prefix3 = med([u["calls"][0]["cw"] + u["calls"][0]["cr"] for u in u3[WI3]])
    res["categories"]["cat3"] = {"rungs": s3, "context_growth": growth, "source": cat3_source, "records": sum(len(u3[r]) for r in order3),
                                 "call_stats": cat3_stats, "quality": q3, "quality_source": q3_source, "handbook_prefix_tokens": prefix3,
                                 "turn_output": {"turns": len(all_turns3), "in_150_600": in_band, "median": med([x["output"] for x in all_turns3]),
                                                 "range": rng([x["output"] for x in all_turns3]), "turns_with_thinking": len(with_thinking)}}
    g = growth[WO3]
    n3 = s3[WO3]["n"]
    claim("Cat 3", "Per-turn context grows 1.2k → 6.5k → 14k → 25k+ (turns 1/3/6/10)", f"without the improvement (mean of n={n3}): {g['turn1']/1e3:.1f}k → {g['turn3']/1e3:.1f}k → {g['turn6']/1e3:.1f}k → {g['turn10']/1e3:.1f}k",
          verdict(False, True), f"Starts much higher (a ~{prefix3/1e3:.1f}k-token handbook is sent on every turn) and grows more slowly: +{g['slope_tokens_per_turn']/1e3:.1f}k/turn vs the ~2.6k/turn the chart implies.")
    claim("Cat 3", "Session 10,000–40,000+ tokens", f"peak context {g['peak_context']/1e3:.1f}k; cumulative billed prompt per session {s3[WO3]['prompt_tokens_median']/1e3:.0f}k (median, n={n3}; without the improvement)",
          verdict(False, True), f"Holds for context-window size. Billed tokens per 10-turn session are ~{s3[WO3]['prompt_tokens_median']/40e3:.0f}× the top of the range, because every turn re-sends the history.")
    to3 = res["categories"]["cat3"]["turn_output"]
    out_med_ok = 150 <= to3["median"] <= 600
    claim("Cat 3", "Output 150–600 tokens per turn",
          f"both versions: median {to3['median']:.0f}, range {to3['range'][0]:,}–{to3['range'][1]:,}; {in_band}/{to3['turns']} turns in 150–600",
          verdict(to3["range"][1] <= 600 and to3["range"][0] >= 150, out_med_ok),
          f"Output tokens include extended thinking, which was non-zero on {to3['turns_with_thinking']}/{to3['turns']} turns, so the same turn varies a lot between repeats. "
          + ("The typical turn is in range; the longest replies are several times the top of it." if out_med_ok else "The typical turn is outside the range."))
    gs = growth[WI3]
    cut_s = pct_saving(s3[WO3]["cost_per_1k_billed"], s3[WI3]["cost_per_1k_billed"])
    bounded = gs["slope_tokens_per_turn"] < g["slope_tokens_per_turn"] and cut_s > 0
    lever_measured = (f"context slope: without +{g['slope_tokens_per_turn']:.0f} tok/turn (turn 10 {g['turn10']/1e3:.1f}k) → with +{gs['slope_tokens_per_turn']:.0f} tok/turn "
                      f"(turn 10 {gs['turn10']/1e3:.1f}k, peak {gs['peak_context']/1e3:.1f}k); cost ${s3[WO3]['cost_per_1k_billed']:.2f} → ${s3[WI3]['cost_per_1k_billed']:.2f} "
                      f"per 1k sessions billed (−{cut_s:.0f}%; n={n3} sessions per version)")
    lever_note = ("Rule: holds if the version with the improvement grows its context more slowly per turn and costs less per session billed. "
                  f"Both hold: the summaries bound the growth from turn {min((t for t in (3, 6, 10) if gs[f'turn{t}'] < g[f'turn{t}']), default=10)} on, and the cached handbook prefix cuts the price of each turn.")
    fr = lambda m: f"{m['hits']}/{m['total']}" if m else "—"  # noqa: E731
    if q3 and WO3 in q3 and WI3 in q3:
        qo, qw = q3[WO3], q3[WI3]
        eo, ew = qo["ledger_by_origin"].get("1-3"), qw["ledger_by_origin"].get("1-3")
        lever_measured += (f"; quality: recall questions {fr(qw['probe_accuracy'])} with vs {fr(qo['probe_accuracy'])} without, "
                           f"turn 1–3 details kept in the final summary {fr(ew)} vs {fr(eo)}")
        lever_note += (" The cost claim holds, but the saving is not free: after compaction the early-turn specifics are no longer in the "
                       "context, and replies to recall questions about them stated that the detail was not available (see the quality table and the implicit-claim row).")
    else:
        lever_note += f" No answer-quality data could be read ({q3_source['reason'] if q3_source.get('reason') else 'the summary has no cell for one of the versions'})."
    claim("Cat 3", "Prefix caching + sliding-window summary prevents quadratic session cost", lever_measured, verdict(bounded), lever_note)
    if q3 and WO3 in q3 and WI3 in q3:
        def worse(a, b):  # a clearly below b: Wilson intervals do not overlap
            return bool(a and b and a["ci_high"] is not None and b["ci_low"] is not None and a["ci_high"] < b["ci_low"])
        measures3 = (("recall questions", lambda q: q["probe_accuracy"]), ("turn 1–3 details in the final summary", lambda q: q["ledger_by_origin"].get("1-3")),
                     ("answers grounded (turns 1–9)", lambda q: q["turn_recall"]))
        lost3 = [n for n, m in measures3 if worse(m(qw), m(qo))]
        lower3 = [n for n, m in measures3 if m(qw) and m(qo) and m(qw)["hits"] / m(qw)["total"] < m(qo)["hits"] / m(qo)["total"]]
        claim("Cat 3", "…without losing answer quality (implicit)",
              f"with vs without the improvement (n={n3} sessions each): answers grounded (turns 1–9) {fr(qw['turn_recall'])} vs {fr(qo['turn_recall'])}; "
              f"recall questions {fr(qw['probe_accuracy'])} vs {fr(qo['probe_accuracy'])}; turn 1–3 details in the final summary {fr(ew)} vs {fr(eo)}",
              implicit_verdict(bool(lost3), not lower3),
              "Answer key, deterministic string matching, 95% Wilson intervals; the reference is the version without the improvement. Replies on turns 1–9 stay "
              "grounded in both versions, but once early turns are compacted, replies to recall questions about them did not give their specifics and the final "
              "summary kept fewer of them. "
              + (f"Implicit-row rule: a clear loss ({', '.join(lost3)}: the intervals do not overlap)." if lost3
                 else (f"Implicit-row rule: no clear loss, but point estimates are lower ({', '.join(lower3)})." if lower3 else "")))
    else:
        claim("Cat 3", "…without losing answer quality (implicit)", "no quality data", "NOT TESTABLE", q3_source.get("reason") or "the summary has no cell for one of the versions")

    # ---------------- Cat 4 (quality rerun: without / with the deck's improvement x 2 corpus sizes x 3 sessions of 8 questions)
    u4, cat4_source, cat4_stats = cat4_units()
    order4 = [_cat4_key(r, sc) for r in CAT4_RUNGS for sc in CAT4_SCALES if u4.get(_cat4_key(r, sc))]
    s4 = summarize_rungs(u4, order4)

    def _cat4_pq(units, summ, key):
        qs = [q for u in units[key] for q in u["per_question"]]
        synth = [q["calls"][-1] for q in qs]  # synthesis is the last call of each question
        return {
            "answers": len(qs),
            "synth_prompt_range": rng([prompt_tokens(c) for c in synth]),
            "synth_prompt_median": med([prompt_tokens(c) for c in synth]),
            "synth_output_range": rng([c["out"] for c in synth]),
            "synth_output_median": med([c["out"] for c in synth]),
            "synth_outputs": [c["out"] for c in synth],
            "io_ratio_median": med([prompt_tokens(c) / c["out"] for c in synth if c["out"]]),
            "cost_per_1k_q_billed": summ[key]["cost_per_1k_billed"] / 4,
            "cost_per_1k_q_warm": summ[key]["cost_per_1k_warm"] / 4,
            "cost_per_1k_q_cold": summ[key]["cost_per_1k_cold"] / 4,
            "cost_per_1k_q_billed_repo_card": summ[key]["cost_per_1k_billed_repo_card"] / 4,
            "citations_median": med([q["citations"] for q in qs]),
            "questions_with_zero_citations": sum(1 for q in qs if q["citations"] == 0),
            "stop_reasons": dict(Counter(str(q["stop_reason"]) for q in qs)),
        }
    per_q = {key: _cat4_pq(u4, s4, key) for key in order4}
    q4, q4_source = cat4_quality()
    res["categories"]["cat4"] = {"rungs": s4, "per_question": per_q, "source": cat4_source, "call_stats": cat4_stats,
                                 "quality": q4, "quality_source": q4_source}
    K = _cat4_key
    NV, PR = CAT4_RUNGS  # without (full corpus, no cache, no citations); with (Haiku picks from the cached corpus -> Sonnet + citations)
    fr4 = lambda m: f"{m['hits']}/{m['total']}" if m else "—"  # noqa: E731
    pc4 = lambda m: f"{m['hits'] / m['total'] * 100:.0f}%" if m and m["total"] else "—"  # noqa: E731
    nq1 = per_q[K(NV, 1)]
    nq3 = per_q.get(K(NV, 3))
    pq1 = per_q.get(K(PR, 1))
    full_rows = [per_q[k] for k in (K(NV, 1), K(NV, 3)) if k in per_q]
    full_lo = min(r["synth_prompt_range"][0] for r in full_rows)
    full_hi = max(r["synth_prompt_range"][1] for r in full_rows)
    claim("Cat 4", "Input 15k–100k+ tokens",
          f"without the improvement (full corpus) {full_lo/1e3:.1f}k–{full_hi/1e3:.1f}k per question (7 documents → 21 documents)"
          + (f"; with the improvement, Sonnet's prompt {pq1['synth_prompt_range'][0]/1e3:.1f}k–{pq1['synth_prompt_range'][1]/1e3:.1f}k (the 5 picked clauses)" if pq1 else ""),
          verdict(full_lo >= 15_000 and full_hi <= 100_000),
          f"n={sum(r['answers'] for r in per_q.values())} answers. Every full-corpus prompt is in the band at both corpus sizes; the version with the improvement cuts "
          "the answering model's prompt below it by design (its Haiku step reads the whole corpus from a cached block).")
    outs = [o for r in per_q.values() for o in r["synth_outputs"]]
    in_band = sum(1 for o in outs if 400 <= o <= 1500)
    out_med = med(outs)
    claim("Cat 4", "Output 400–1,500 tokens",
          f"all {len(outs)} answers: median {out_med:.0f}, range {min(outs):,}–{max(outs):,}; {in_band}/{len(outs)} in 400–1,500",
          verdict(min(outs) >= 400 and max(outs) <= 1500, 400 <= out_med <= 1500),
          "Output tokens include extended thinking. "
          + (f"{cat4_stats['synthesis_outputs_above_app_cap_before']} answers used more than 2,048 output tokens (the synthesis cap is 4,096). " if cat4_stats else ""))
    r3 = nq3["io_ratio_median"] if nq3 else None
    claim("Cat 4", "Input:output ≈ 20:1 to 100:1",
          f"full-corpus median {nq1['io_ratio_median']:.1f}:1 (7 documents)" + (f", {r3:.1f}:1 (21 documents)" if r3 else ""),
          verdict(all(x is not None and 20 <= x <= 100 for x in (nq1["io_ratio_median"], r3)), any(x is not None and 20 <= x <= 100 for x in (nq1["io_ratio_median"], r3))),
          "Grows with the corpus: at the 7-document deal room it sits at the 20:1 floor; at 3× it is inside the range.")

    def worse(a, b):  # a clearly above b: Wilson intervals do not overlap
        return bool(a and b and a.get("ci_low") is not None and b.get("ci_high") is not None and a["ci_low"] > b["ci_high"])
    have4 = q4 and all(K(r, sc) in q4 and K(r, sc) in per_q for r in CAT4_RUNGS for sc in CAT4_SCALES)
    if have4:
        n1, n3q = q4[K(NV, 1)], q4[K(NV, 3)]
        p1, p3 = q4[K(PR, 1)], q4[K(PR, 3)]
        cost = lambda r, sc: per_q[K(r, sc)]["cost_per_1k_q_billed"] / 1000  # noqa: E731
        # lever row. Rule (both corpus sizes, with vs without at the same size; "clearly" = 95% Wilson intervals do not
        # overlap): retrieval holds = the picked clauses hold the expected clauses (share not clearly below the full
        # corpus's 100%) and no other supplier's clause is picked; cost holds = cheaper per question billed in
        # 8-question sessions; quality holds = share of answers with a serious error not clearly higher.
        full = lambda m: {"hits": m["total"], "total": m["total"], **dict(zip(("ci_low", "ci_high"), wilson(m["total"], m["total"])))}  # noqa: E731
        retr_ok = all(p["recall_after_rerank"] and not worse(full(p["recall_after_rerank"]), p["recall_after_rerank"])
                      and (p["distractors_selected"] or {}).get("hits", 0) == 0 for p in (p1, p3))
        cost_ok = all(cost(PR, sc) < cost(NV, sc) for sc in CAT4_SCALES)
        q_worse = {sc: worse(q4[K(PR, sc)]["answers_with_material_error"], q4[K(NV, sc)]["answers_with_material_error"]) for sc in CAT4_SCALES}
        quality_ok = not any(q_worse.values())
        measured = (f"with the improvement (Haiku picks 5 clauses from the cached full corpus, Sonnet answers over them with citations; n=24 per corpus size) vs without "
                    f"(full corpus, no cache, no citations): expected clauses among the picks {pc4(p1['recall_after_rerank'])} / {pc4(p3['recall_after_rerank'])} "
                    f"(7 / 21 documents); other suppliers' clauses picked {fr4(p1['distractors_selected'])} / {fr4(p3['distractors_selected'])}; "
                    f"$/question billed ${cost(PR, 1):.4f} / ${cost(PR, 3):.4f} vs ${cost(NV, 1):.4f} / ${cost(NV, 3):.4f} "
                    f"(−{pct_saving(cost(NV, 1), cost(PR, 1)):.0f}% / −{pct_saving(cost(NV, 3), cost(PR, 3)):.0f}%); "
                    f"answers with a serious error {fr4(p1['answers_with_material_error'])} / {fr4(p3['answers_with_material_error'])} vs "
                    f"{fr4(n1['answers_with_material_error'])} / {fr4(n3q['answers_with_material_error'])}")
        note = ("Rule (both corpus sizes, with vs without the improvement at the same size; \"clearly\" = 95% Wilson intervals do not overlap): retrieval holds if the "
                "picked clauses' share of expected clauses is not clearly below the full corpus's (which holds every clause) and no other supplier's clause is picked; "
                "cost holds if it is cheaper per question billed in 8-question sessions; quality holds if its share of answers with a serious error is not clearly higher. "
                f"Retrieval {'holds' if retr_ok else 'does not hold'}; cost {'holds' if cost_ok else 'does not hold'}; quality "
                + ("holds" if quality_ok else "does not hold (" + ", ".join(f"{CAT4_SCALE_LABEL[sc]}" for sc, w in q_worse.items() if w) + ")") + ".")
        claim("Cat 4", "Pair hybrid retrieval (reranking + chunk filtering) with context caching", measured,
              verdict(retr_ok and cost_ok and quality_ok, retr_ok or cost_ok), note)
        # implicit quality row: with vs without at the same corpus size (same Wilson rule)
        clear = [sc for sc in CAT4_SCALES if worse(q4[K(PR, sc)]["answers_with_material_error"], q4[K(NV, sc)]["answers_with_material_error"])]
        rate = lambda m: (m or {}).get("hits", 0) / ((m or {}).get("total") or 1)  # noqa: E731
        lower4 = []
        for sc in CAT4_SCALES:
            a, b = q4[K(PR, sc)], q4[K(NV, sc)]
            low = ([("serious errors", f"{fr4(a['answers_with_material_error'])} vs {fr4(b['answers_with_material_error'])}")]
                   if rate(a["answers_with_material_error"]) > rate(b["answers_with_material_error"]) else [])
            low += [("correctness", f"{a['correctness_mean']:.2f} vs {b['correctness_mean']:.2f}")] if a["correctness_mean"] < b["correctness_mean"] else []
            low += [("key facts", f"{fr4(a['fact_recall'])} vs {fr4(b['fact_recall'])}")] if rate(a["fact_recall"]) < rate(b["fact_recall"]) else []
            if low:
                lower4.append(f"{CAT4_SCALE_LABEL[sc]}: " + ", ".join(f"{n} {v}" for n, v in low))
        v_impl4 = implicit_verdict(bool(clear), not lower4)
        claim("Cat 4", "…without losing answer quality (implicit)",
              f"with vs without the improvement (7 / 21 documents, n=24 answers each): answers with a serious error {fr4(p1['answers_with_material_error'])} / "
              f"{fr4(p3['answers_with_material_error'])} vs {fr4(n1['answers_with_material_error'])} / {fr4(n3q['answers_with_material_error'])}; grader correctness "
              f"{p1['correctness_mean']:.2f} / {p3['correctness_mean']:.2f} vs {n1['correctness_mean']:.2f} / {n3q['correctness_mean']:.2f}; key facts "
              f"{fr4(p1['fact_recall'])} / {fr4(p3['fact_recall'])} vs {fr4(n1['fact_recall'])} / {fr4(n3q['fact_recall'])}",
              v_impl4,
              "Reference: the version without the improvement (full corpus, no cache, no citations) at the same corpus size. Clear loss: the share of answers with a "
              "serious error is clearly higher (95% Wilson intervals do not overlap). "
              + ("A clear loss at " + ", ".join(CAT4_SCALE_LABEL[sc] for sc in clear) + ". " if clear else "No clear loss at either size. ")
              + ("Implicit-row rule: no clear loss is detected, but point estimates are lower (" + "; ".join(lower4) + "), and 24 answers per cell cannot show "
                 "the versions are equal, so the row is PARTLY. " if v_impl4 == "PARTLY SUPPORTED" else "")
              + "Blind grader, one pass per answer; the deterministic key facts move less than the grader's error count.")
    else:
        claim("Cat 4", "Pair hybrid retrieval (reranking + chunk filtering) with context caching", "no rerun data for both versions at both corpus sizes", "NOT TESTABLE",
              q4_source.get("reason") or "the Category 4 rerun summary lacks a cell")
        claim("Cat 4", "…without losing answer quality (implicit)", "no quality data", "NOT TESTABLE", q4_source.get("reason") or "")

    # ---------------- Cat 5 (without / with the deck's lever x Sonnet / Haiku: 4 cells x 12 invoices x 3 repeats)
    info5, info5_source = cat5_ablation_info()
    u5 = None
    if info5 and info5.get("run_ids") and CAT5_ABLATION.is_file():
        try:
            u5 = cat5_ablation_units(info5["run_ids"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            u5 = None
    if u5 and all(u5.get(a) for a in CAT5_REQUIRED_ARMS) and all(a in info5["arms"] for a in CAT5_REQUIRED_ARMS):
        WO5, WOH5, WS5, WH5 = CAT5_ARMS  # without: Sonnet, Haiku; with: Sonnet, Haiku-first
        order5 = [a for a in CAT5_ARMS if u5.get(a) and a in info5["arms"]]  # recorded cells
        pend_cells5 = [a for a in CAT5_ARMS if a not in order5]  # cells with no run recorded yet ("run pending")
        s5 = summarize_rungs(u5, order5)
        a5 = info5["arms"]
        q5 = {a: {"runs": a5[a]["runs"], "exact": a5[a]["exact"], "decision_correct": a5[a]["decision_correct"],
                  "exact_ci": list(wilson(a5[a]["exact"], a5[a]["runs"])), "turns_mean": st.mean(u["steps"] for u in u5[a]),
                  "turns_max": max(u["steps"] for u in u5[a]), "turn_cap": a5[a]["turn_cap"],
                  "cap_hits": sum(1 for u in u5[a] if u["cap_hit"]), "escalations": sum(1 for u in u5[a] if u["escalated"]),
                  "escalation_expected": a5[a]["escalation_expected"], "truncated_turns": a5[a]["truncated_turns"],
                  "expected_runs": a5[a]["expected_runs"], "pending_runs": a5[a]["pending_runs"],
                  "summary_cost_billed": a5[a]["summary_cost_billed"]} for a in order5}
        # while a recorded cell has pending runs, every comparison uses the invoices recorded in all recorded cells
        common5 = sorted(set.intersection(*({u["preset_id"] for u in u5[a]} for a in order5)))
        pending5 = sum(q5[a]["pending_runs"] for a in order5)
        pending_inv5 = sorted({p for a in order5 for p in a5[a]["pending_invoices"]})
        cu5 = {a: [u for u in u5[a] if u["preset_id"] in common5] for a in order5}
        cs5 = summarize_rungs(cu5, order5)
        cq5 = {}
        for a in order5:
            bi = a5[a]["by_invoice"]
            k = sum(bi[p][0] for p in common5) if bi and all(p in bi for p in common5) else q5[a]["exact"]
            cq5[a] = {"exact": k, "runs": len(cu5[a]), "ci": list(wilson(k, len(cu5[a]))),
                      "turns_mean": st.mean(u["steps"] for u in cu5[a]), "escalations": sum(1 for u in cu5[a] if u["escalated"])}

        def cmp5(old, new):
            if old not in cq5 or new not in cq5:
                return None  # a cell is pending: no comparison yet
            out = {"from": old, "to": new, "exact_from": cq5[old]["exact"], "exact_to": cq5[new]["exact"], "runs": cq5[new]["runs"],
                   "turns_from": cq5[old]["turns_mean"], "turns_to": cq5[new]["turns_mean"],
                   "clear_loss": cq5[new]["ci"][1] < cq5[old]["ci"][0],
                   "not_lower": cq5[new]["exact"] / cq5[new]["runs"] >= cq5[old]["exact"] / cq5[old]["runs"]}
            for v in ("billed", "warm", "cold"):
                f, t = cs5[old][f"cost_per_1k_{v}"], cs5[new][f"cost_per_1k_{v}"]
                out[f"{v}_from"], out[f"{v}_to"], out[f"{v}_change_pct"] = f, t, (t / f - 1) * 100 if f else None
            return out
        # (name, older/costlier cell, cheaper cell): the lever on each model set-up; the smaller model on each design
        pairs5 = {"with vs without the lever, Sonnet": cmp5(WO5, WS5),
                  "with vs without the lever, Haiku (Haiku-first with it)": cmp5(WOH5, WH5),
                  "Haiku vs Sonnet, without the lever": cmp5(WO5, WOH5),
                  "Haiku-first vs Sonnet, with the lever": cmp5(WS5, WH5)}
        cost_check = max(abs(s5[a]["cost_per_1k_billed"] - (q5[a]["summary_cost_billed"] or 0)) for a in order5)
        res["categories"]["cat5"] = {"rungs": s5, "quality": q5, "source": "ablation", "summary_source": info5_source,
                                     "records": sum(len(u5[a]) for a in order5), "invoices_pooled": info5["invoices_pooled"],
                                     "repeats": info5["repeats"], "settings": info5["settings"], "data_quality": info5["data_quality"],
                                     "non_exact_runs": info5["non_exact_runs"], "pending_runs": pending5, "pending_invoices": pending_inv5,
                                     "pending_cells": pend_cells5, "common_invoices": common5, "comparisons": pairs5,
                                     "max_cost_diff_vs_summary_per_1k": cost_check, "app_rungs": dict(CAT5_ARM_FOR_RUNG)}
        on5 = (f" (compared on the {len(common5)} invoices recorded in every cell; {pending5} runs not recorded yet)" if pending5 else "")
        pend_note5 = ("".join(f"{CAT5_LABELS[a].split(' (')[0]}: run pending (no runs recorded yet), so this row uses the "
                              f"{len(order5)} recorded cells. " for a in pend_cells5))
        cell5 = lambda a, fn: fn(a) if a in order5 else "run pending"  # noqa: E731
        runs_txt5 = "/".join(str(q5[a]["runs"]) if a in order5 else "0" for a in CAT5_ARMS)
        rk5 = lambda a: f"{s5[a]['prompt_tokens_range'][0]/1e3:.0f}k–{s5[a]['prompt_tokens_range'][1]/1e3:.0f}k"  # noqa: E731
        claim("Cat 5", "Input 25k–150k+ tokens per task",
              f"n={runs_txt5} runs: " + "; ".join(f"{CAT5_LABELS[a]} {cell5(a, rk5)}" for a in CAT5_ARMS),
              verdict(min(s5[a]["prompt_tokens_range"][0] for a in order5) >= 25_000, s5[WO5]["prompt_tokens_range"][0] >= 25_000),
              pend_note5 + ("Every recorded cell is in the band. " if pend_cells5 else "Every cell is in the band. ")
              + "With the lever, most of it is cache reads of the policy manual resent each turn: uncached input per invoice "
              "(median) is " + "; ".join(f"{CAT5_LABELS[a].split(' (')[0]} {_k(med([sum(c['in'] for c in u['calls']) for u in u5[a]]))}" for a in order5) + ".")
        all_out = [tok(u["calls"])["output"] for a in order5 for u in u5[a]]
        in_band5 = sum(1 for o in all_out if 1500 <= o <= 8000)
        tl5 = sorted({u["steps"] for a in order5 for u in u5[a]})
        ok5 = lambda a: f"{s5[a]['output_tokens_range'][0]:,}–{s5[a]['output_tokens_range'][1]:,}"  # noqa: E731
        claim("Cat 5", "Output 1,500–8,000 tokens per task",
              "; ".join(f"{CAT5_LABELS[a]} {cell5(a, ok5)}" for a in CAT5_ARMS) + f"; {in_band5}/{len(all_out)} runs in band",
              verdict(in_band5 == len(all_out), in_band5 > 0),
              pend_note5 + f"Median {med(all_out):,.0f} output tokens per invoice; output includes extended thinking (Sonnet only). "
              f"These are short {tl5[0]}–{tl5[-1]}-turn loops.")

        # lever row: the deck's lever judged as a whole in three parts. The guardrail part compares with vs without the lever
        # on each model set-up; the routing part compares Haiku with Sonnet on each design, so the model and the design
        # are separated once both Haiku cells exist.
        def pair_text(name, c):
            if c is None:
                return f"{name}: run pending"
            return (f"{name}: cost {c['billed_change_pct']:+.0f}% billed ({_money(c['billed_from'])} → {_money(c['billed_to'])}/1k; "
                    f"warm {_money(c['warm_from'])} → {_money(c['warm_to'])}), turns {c['turns_from']:.1f} → {c['turns_to']:.1f}, "
                    f"exact vouchers {c['exact_from']}/{c['runs']} → {c['exact_to']}/{c['runs']}")

        def gate_ok(c):  # the written rule used before: cost up with no accuracy gain, or a clear loss, contradicts the part
            return not (c["clear_loss"] or (c["billed_change_pct"] > 0 and c["exact_to"] <= c["exact_from"]))

        def route_ok(c):
            return c["billed_change_pct"] < 0 and c["not_lower"]

        def combine(oks):
            return "SUPPORTED" if all(oks) else ("NOT SUPPORTED" if not any(oks) else "PARTLY SUPPORTED")

        caps5 = sum(q5[a]["cap_hits"] for a in order5)
        wo_max, wo_cap = max(q5[a]["turns_max"] for a in (WO5, WOH5) if a in q5), q5[WO5]["turn_cap"]
        w_turns, w_cap = q5[WS5]["turns_mean"], q5[WS5]["turn_cap"]
        esc5 = cq5[WH5]["escalations"]
        g_names = ["with vs without the lever, Sonnet", "with vs without the lever, Haiku (Haiku-first with it)"]
        r_names = ["Haiku vs Sonnet, without the lever", "Haiku-first vs Sonnet, with the lever"]
        g_have = [n for n in g_names if pairs5[n]]
        r_have = [n for n in r_names if pairs5[n]]
        budget_part = (f"max-step budgets: {caps5} of {sum(q5[a]['runs'] for a in order5)} runs hit a cap; without the lever ({wo_cap}-turn safety cap) "
                       f"runs finished in at most {wo_max} turns, with it in {w_turns:.0f} of {w_cap}")
        p_budget = "NOT SHOWN" if caps5 == 0 else "SUPPORTED"
        p_gate = combine([gate_ok(pairs5[n]) for n in g_have])
        p_route = combine([route_ok(pairs5[n]) for n in r_have])
        parts5 = [p_budget, p_gate, p_route]
        v_lever = ("SUPPORTED" if all(x == "SUPPORTED" for x in parts5) else
                   "PARTLY SUPPORTED" if any(x in ("SUPPORTED", "PARTLY SUPPORTED") for x in parts5) else "NOT SUPPORTED")
        word = {"SUPPORTED": "supported", "NOT SUPPORTED": "not supported", "NOT SHOWN": "not shown", "PARTLY SUPPORTED": "partly supported"}
        note_b = ("no loop ran long on these invoices, so a budget saved nothing here; whether it prevents runaway cost is untested"
                  if p_budget == "NOT SHOWN" else f"{caps5} runs reached a cap")

        def brief(n):
            c = pairs5[n]
            return f"{n}, cost {c['billed_change_pct']:+.0f}% and exact vouchers {c['exact_from']} → {c['exact_to']} of {c['runs']}"
        note_g = ("; ".join(brief(n) for n in g_have)
                  + (" (the Haiku column is pending)" if len(g_have) < len(g_names) else "")
                  + ". The with-design also replaces the raw tables with one narrow query and sends the policy manual as a cached prefix, so the saving "
                  "belongs to the design as a whole and these cells cannot split it between the guardrail and those changes")
        note_r = ("; ".join(brief(n) for n in r_have)
                  + f"; with the lever the Haiku-first version switched to Sonnet in {esc5} of {cq5[WH5]['runs']} runs, the runs where the policy tool "
                  "flags a multi-factor dispute (manual 6.2); without it there is no policy tool and so no escalation path"
                  + ("" if len(r_have) == len(r_names) else
                     ". The Haiku cell without the lever is pending, so the model cannot yet be separated from the design"))
        claim("Cat 5", "Max-step budgets + deterministic guardrails + small-model routing for routine tool calls",
              "; ".join([budget_part, *(pair_text(n, pairs5[n]) for n in g_names + r_names)]) + on5,
              v_lever,
              pend_note5 + f"Judged as a whole in three parts. (1) Step budgets: {word[p_budget]} — {note_b}. (2) Deterministic guardrails (with vs without "
              f"the lever on the same model set-up): {word[p_gate]} — {note_g}. (3) Small-model routing (Haiku vs Sonnet on the same design): "
              f"{word[p_route]} — {note_r}. "
              f"As a whole: {sum(x == 'SUPPORTED' for x in parts5)} of 3 parts supported, {sum(x == 'PARTLY SUPPORTED' for x in parts5)} partly, "
              f"{sum(x == 'NOT SUPPORTED' for x in parts5)} contradicted, {sum(x == 'NOT SHOWN' for x in parts5)} never came into play.")
        res["categories"]["cat5"]["lever_parts"] = {"max_step_budgets": p_budget, "deterministic_guardrails": p_gate, "small_model_routing": p_route}
        have5 = [n for n in g_names + r_names if pairs5[n]]
        ceiling5 = all(cq5[a]["exact"] == cq5[a]["runs"] for a in order5)
        lower5 = [n for n in have5 if not pairs5[n]["not_lower"]]
        claim("Cat 5", "…without losing accuracy (implicit)",
              "exact vouchers: " + "; ".join(
                  (f"{n} {pairs5[n]['exact_to']}/{pairs5[n]['runs']} vs {pairs5[n]['exact_from']}/{pairs5[n]['runs']}" if pairs5[n] else f"{n} run pending")
                  for n in g_names + r_names) + on5,
              implicit_verdict(any(pairs5[n]["clear_loss"] for n in have5), all(pairs5[n]["not_lower"] for n in have5), ceiling=ceiling5),
              pend_note5 + "Compared under the written rule: the lever against the same task without it on each model set-up, and Haiku against Sonnet "
              "with and without the lever" + (" (comparisons with a pending cell are not made yet). " if pend_cells5 else ". ")
              + ("Every compared run committed the exact voucher, so a loss could not be detected (ceiling); the invoices test simple arithmetic"
                 if ceiling5 else
                 (("Fewer exact vouchers in the second-named cell (with the lever, or Haiku) of: " + "; ".join(lower5) + " (a clear loss needs "
                   "non-overlapping 95% Wilson intervals). ") if lower5 else "") + "The invoices test simple arithmetic")
              + " (quantities × rates, a GST split, a debit note). All recorded runs: "
              + "; ".join(f"{CAT5_LABELS[a].split(' (')[0]} {q5[a]['exact']}/{q5[a]['runs']}" for a in order5) + ".")
    else:
        u5 = cat5_golden_units(seeds)
        order5 = [r for r in CAT5_APP_RUNGS if u5.get(r)]
        s5 = summarize_rungs(u5, order5)
        q5 = {r: {"exact_match": sum(1 for u in u5[r] if (u["evaluation"] or {}).get("exact_match")),
                  "steps": [u["steps"] for u in u5[r]], "escalations": sum(1 for u in u5[r] if u["escalated"])} for r in order5}
        reason5 = info5_source if not info5 else "the ablation records (backend/experiments/cat5_ablation/runs.jsonl) could not be read"
        res["categories"]["cat5"] = {"rungs": s5, "quality": q5, "source": "golden replays", "summary_source": info5_source, "reason": reason5}
        ub5 = s5["unbounded_sonnet_loop"]
        claim("Cat 5", "Input 25k–150k+ tokens per task", f"unbounded {ub5['prompt_tokens_range'][0]/1e3:.0f}k–{ub5['prompt_tokens_range'][1]/1e3:.0f}k (golden replays, n=3)",
              verdict(ub5["prompt_tokens_range"][0] >= 25_000), "Golden replays only: " + reason5 + ".")
        claim("Cat 5", "Output 1,500–8,000 tokens per task", f"unbounded {ub5['output_tokens_range'][0]:,}–{ub5['output_tokens_range'][1]:,} (golden replays, n=3)",
              verdict(False, True), "Golden replays only: " + reason5 + ".")
        claim("Cat 5", "Max-step budgets + deterministic guardrails + small-model routing for routine tool calls", "no ablation data", "NOT TESTABLE",
              "Three invoices cannot separate the levers; " + reason5 + ".")
        claim("Cat 5", "…without losing accuracy (implicit)", "no ablation data", "NOT TESTABLE", reason5)

    # ---------------- Cat 6 (fair rerun: 4 cells x 3 incidents x 5 repeats; with / without the deck's lever x model set-up)
    u6 = cat6_units()
    order6 = [a for a in CAT6_ARMS if u6.get(a)]  # recorded cells; a cell with no runs yet is "run pending"
    pending6 = [a for a in CAT6_ARMS if not u6.get(a)]
    s6 = summarize_rungs(u6, order6)
    cpo = {}
    for r in order6:
        verified = sum(1 for u in u6[r] if u["verified"])
        totals = {v: sum(unit_cost(u["calls"], view=v) for u in u6[r]) for v in ("billed", "warm", "cold")}
        cpo[r] = {"verified": verified, "first_attempt_verified": sum(1 for u in u6[r] if u["first_verified"]), "runs": len(u6[r]),
                  "checks_passed": sum(u["passed"] or 0 for u in u6[r]), "checks_total": sum(u["checks"] or 0 for u in u6[r]),
                  "cost_per_run": totals["billed"] / len(u6[r]),
                  "cpo": totals["billed"] / verified if verified else None,
                  "cpo_warm": totals["warm"] / verified if verified else None,
                  "cpo_cold": totals["cold"] / verified if verified else None,
                  "turns_at_max_tokens": sum(u["turns_at_max_tokens"] for u in u6[r]),
                  "turns_total": sum(len(u["calls"]) for u in u6[r]),
                  "retries_triggered": sum(1 for u in u6[r] if u["retries"] > 0),
                  "cost_per_run_warm": totals["warm"] / len(u6[r]), "cost_per_run_cold": totals["cold"] / len(u6[r]),
                  "model_s_mean": st.mean(u["model_ms"] for u in u6[r]) / 1000,
                  "mean_total_tokens": st.mean(tok(u["calls"])["total"] for u in u6[r])}
    prefix6 = med([u["turn1_prefix"] for u in u6["isolated_cached_gate"]])
    res["categories"]["cat6"] = {"rungs": s6, "cpo": cpo, "source": "fair rerun",
                                 "records": sum(len(u6[r]) for r in order6), "repo_prefix_tokens": prefix6, "pending": pending6}
    SB6, SBT6, ISO6, TI6 = CAT6_ARMS
    n6 = cpo[SB6]["runs"]
    pend6 = ("; ".join(f"{CAT6_CELL[a][0].upper()}{CAT6_CELL[a][1:]}: {CAT6_RUN_PENDING}" for a in pending6)
             + f" (no runs recorded yet), so this row uses the {len(order6)} recorded cells. ") if pending6 else ""

    def per_cell6(fmt):
        return "; ".join(f"{CAT6_CELL[a]} {fmt(a) if a in s6 else CAT6_RUN_PENDING}" for a in CAT6_ARMS)

    rk = lambda a: f"{s6[a]['prompt_tokens_range'][0]/1e3:.0f}k–{s6[a]['prompt_tokens_range'][1]/1e3:.0f}k"  # noqa: E731
    in_band6 = [a for a in order6 if s6[a]["prompt_tokens_range"][0] >= 100_000]
    wo_in6 = all(a in in_band6 for a in (SB6, SBT6) if a in s6)
    claim("Cat 6", "Input 100k–1M+ tokens per run",
          f"n={n6} runs per cell: " + per_cell6(rk),
          verdict(len(in_band6) == len(order6), bool(in_band6)),
          pend6 + ("Without the lever every run is in the band, all of it uncached. " if wo_in6 else "Without the lever some runs are below the band. ")
          + f"With it, each run sends ~{s6[ISO6]['prompt_tokens_median']/1e3:.0f}k, mostly cache reads of a ~{prefix6/1e3:.1f}k-token repo prefix"
          + (", below the band." if all(s6[a]["prompt_tokens_range"][1] < 100_000 for a in (ISO6, TI6) if a in s6) else "."))
    rk1 = lambda a: f"{s6[a]['output_tokens_range'][0]/1e3:.1f}k–{s6[a]['output_tokens_range'][1]/1e3:.1f}k"  # noqa: E731
    mt6 = sum(cpo[a]["turns_at_max_tokens"] for a in order6)
    tlen = sorted({len(u["calls"]) for a in order6 for u in u6[a]})
    turns6 = f"{tlen[0]}" if len(tlen) == 1 else f"{tlen[0]}–{tlen[-1]}"
    out_in6 = sum(1 for a in order6 for u in u6[a] if tok(u["calls"])["output"] >= 10_000)
    out_n6 = sum(len(u6[a]) for a in order6)
    out_lo6 = min(s6[a]["output_tokens_range"][0] for a in order6) / 1e3
    out_hi6 = -(-max(s6[a]["output_tokens_range"][1] for a in order6) // 1000)
    claim("Cat 6", "Output 10k–50k+ tokens per run",
          per_cell6(rk1) + f"; {out_in6}/{out_n6} runs in band",
          verdict(out_in6 == out_n6, 0 < out_in6 < out_n6),
          pend6 + (f"Every cell writes ~{out_lo6:.0f}–{out_hi6:.0f}k per run, below the band; " if out_in6 == 0 else f"{out_in6} of {out_n6} runs reach the band; ")
          + "the role prompts' word limits, the same in every cell, set the length. "
          f"{mt6} of {sum(cpo[a]['turns_total'] for a in order6)} turns stopped on max_tokens. All runs are {turns6} turns on a single-file fix.")
    runs_day6 = lambda a: (f"~{1.5e6/cpo[a]['mean_total_tokens']:.0f}–{10e6/cpo[a]['mean_total_tokens']:.0f} runs/dev/day "  # noqa: E731
                           f"(mean {cpo[a]['mean_total_tokens']/1e3:.0f}k tokens/run)")
    claim("Cat 6", "1.5M–10M+ tokens per developer per day", f"not measurable: {res['categories']['cat6']['records']} single runs, no per-developer daily traffic", "NOT TESTABLE",
          f"Would take {runs_day6(SB6)} without the lever on Sonnet"
          + (f", {runs_day6(SBT6)} without it on Haiku agents + Sonnet patch author" if SBT6 in cpo else "")
          + f", or {runs_day6(TI6)} with it on Haiku agents + Sonnet patch author.")
    # Comparisons (cheaper cell, cell it replaces): the lever on each model column; Haiku agents + Sonnet patch author
    # against Sonnet on each row. A comparison with a pending cell is not made.
    lever6 = [(ISO6, SB6, "Sonnet"), (TI6, SBT6, "Haiku agents + Sonnet patch author")]
    model6 = [(SBT6, SB6, "without the lever"), (TI6, ISO6, "with the lever")]
    lever6_m = [(w, wo, col) for w, wo, col in lever6 if w in cpo and wo in cpo]
    model6_m = [(h, s, row) for h, s, row in model6 if h in cpo and s in cpo]

    def cpo_change6(new, old, key="cpo"):
        a, b = cpo[old][key], cpo[new][key]
        if a is None or b is None:
            return f"{_money(a)} → {_money(b)} (undefined with no verified run)"
        return f"{_money(a)} → {_money(b)}, ~{a / b:.1f}× lower" if b < a else f"{_money(a)} → {_money(b)}, ~{b / a:.1f}× higher"

    def lower6(new, old):
        return cpo[new]["cpo"] is not None and (cpo[old]["cpo"] is None or cpo[new]["cpo"] < cpo[old]["cpo"])

    same_rate = len({cpo[a]["verified"] / cpo[a]["runs"] for a in order6}) == 1
    claim("Cat 6", "Isolate sub-agent contexts, cache the shared repo prefix, measure cost per verified outcome (CpO)",
          "CpO per verified fix (billed): " + "; ".join(
              f"{RUNG_LABELS[a]} {_money(cpo[a]['cpo'])} ({cpo[a]['verified']}/{cpo[a]['runs']} verified)" if a in cpo else f"{RUNG_LABELS[a]} {CAT6_RUN_PENDING}"
              for a in CAT6_ARMS),
          verdict(False, bool(lever6_m) and all(lower6(w, wo) for w, wo, _ in lever6_m)),
          pend6 + "With vs without the lever, cost per verified fix: "
          + "; ".join(f"{col} {cpo_change6(w, wo)} (warm {cpo_change6(w, wo, 'cpo_warm')})" for w, wo, col in lever6_m)
          + (f"; Haiku agents + Sonnet patch author: the without-the-lever cell is pending (with the lever against the shared bus on Sonnet: "
             f"{cpo_change6(TI6, SB6)})" if SBT6 not in cpo and TI6 in cpo else "")
          + ". Haiku agents + Sonnet patch author against Sonnet: "
          + "; ".join(f"{row} {cpo_change6(h, s)}" for h, s, row in model6_m) + ". "
          + ("The verified rate is the same in every cell, so every saving is cost per run and CpO adds nothing over it here (ceiling): "
             "the outcome side of the claim is untested." if same_rate else
             "The verified rate differs between cells, so CpO and cost per run differ; the verified counts are compared in the next row."))
    v6 = {a: (cpo[a]["verified"], cpo[a]["runs"]) for a in order6}
    lo6 = {a: wilson(*v6[a])[0] for a in order6}
    hi6 = {a: wilson(*v6[a])[1] for a in order6}
    pairs6 = [(w, wo) for w, wo, _ in lever6_m] + [(h, s) for h, s, _ in model6_m]
    clear6 = any(hi6[new] < lo6[old] for new, old in pairs6)
    equal6 = all(v6[new][0] / v6[new][1] >= v6[old][0] / v6[old][1] for new, old in pairs6)
    ceiling6 = all(v6[a][0] == v6[a][1] for a in order6)
    vf6 = lambda a: f"{v6[a][0]}/{v6[a][1]}" if a in v6 else CAT6_RUN_PENDING  # noqa: E731
    claim("Cat 6", "…without losing verified fixes (implicit)",
          "with vs without the lever: " + "; ".join(f"{col} {vf6(w)} vs {vf6(wo)}" for w, wo, col in lever6)
          + "; Haiku agents + Sonnet patch author vs Sonnet: " + "; ".join(f"{row} {vf6(h)} vs {vf6(s)}" for h, s, row in model6)
          + " verified final patches",
          implicit_verdict(clear6, equal6, ceiling=ceiling6),
          pend6
          + (f"Every {'recorded ' if pending6 else ''}cell verified every run, so a loss could not be detected (ceiling) on these single-file incidents. " if ceiling6 else "")
          + ("Lower verified count in the cheaper cell: " + "; ".join(
              f"{CAT6_CELL[new]} against {CAT6_CELL[old]} ({vf6(new)} vs {vf6(old)})" for new, old in pairs6
              if v6[new][0] / v6[new][1] < v6[old][0] / v6[old][1]) + ". " if not equal6 else "")
          + "Compared under the written rule: the lever against the same swarm without it on each model set-up, and Haiku agents + a Sonnet patch "
          "author against Sonnet with and without the lever" + (" (comparisons with a pending cell are not made yet)." if pending6 else "."))

    # ---------------- cross-category scale
    s1 = res["categories"]["cat1"].get("rungs") or {}
    scale = {
        **({"Cat 1 (item)": s1["haiku_schema"]["total_tokens_median"]} if "haiku_schema" in s1 else {}),
        "Cat 2 (document)": s2["sonnet_unbounded" if "sonnet_unbounded" in s2 else "sonnet_templated"]["total_tokens_median"],
        "Cat 3 (10-turn session)": s3["naive_full_history"]["total_tokens_median"],
        "Cat 4 (4-question audit)": s4[_cat4_key("naive_full_corpus", 1)]["total_tokens_median"],
        "Cat 4 (single question)": med([tok(q["calls"])["total"] for u in u4[_cat4_key("naive_full_corpus", 1)] for q in u["per_question"]]),
        **({"Cat 4 (single question, 3× corpus)": med([tok(q["calls"])["total"] for u in u4[_cat4_key("naive_full_corpus", 3)] for q in u["per_question"]])}
           if u4.get(_cat4_key("naive_full_corpus", 3)) else {}),
        "Cat 5 (invoice, raw tables)": s5["raw_free_sonnet" if "raw_free_sonnet" in s5 else "unbounded_sonnet_loop"]["total_tokens_median"],
        "Cat 6 (incident run, shared bus)": s6["shared_bus_matched_gate"]["total_tokens_median"],
    }
    res["scale"] = scale
    claim("Matrix", "Monotonic token scale: Cat 1 < Cat 2 < Cat 3 < Cat 4 < Cat 5 << Cat 6",
          "; ".join(f"{k} {v/1e3:.1f}k" for k, v in scale.items()), verdict(False, True),
          "1 < 2 < {3,4,5} < 6 holds. The order of 3, 4 and 5 depends on the unit: a 10-turn session bills more than a single RAG question or a whole invoice.")

    long_haiku = [(cat, r) for cat, us in (("cat1", u1 or {}), ("cat3", u3), ("cat4", u4), ("cat5", u5), ("cat6", u6))
                  for r, lst in us.items() for u in lst for c in u["calls"] if c["model"] == HAIKU and prompt_tokens(c) > HAIKU_LONG_PROMPT_THRESHOLD]
    res["haiku_calls_over_100k_prompt"] = len(long_haiku)
    return res


# ------------------------------------------------------------------ 4. writers
RUNG_LABELS = {
    "sonnet_naive": "Sonnet 5.5 · free-text prose", "haiku_naive": "Haiku 5.5 · free-text prose",
    "haiku_calibrated": "Haiku 5.5 · strict JSON schema",
    "haiku_calibrated_batch": "Haiku 5.5 · strict JSON · Batch API (−50%)",
    "sonnet_unbounded": "Sonnet 5.5 · without: unbounded long-form draft", "haiku_unbounded": "Haiku 5.5 · without: unbounded long-form draft",
    "sonnet_templated": "Sonnet 5.5 · with: section template with length caps", "haiku_templated": "Haiku 5.5 · with: section template with length caps",
    "naive_full_history": "Without the improvement: full history, no cache",
    "prefix_cached_summarized": "With the improvement: cached prefix + sliding-window summaries",
    "naive_full_corpus": "Without the improvement: full corpus, no cache, no citations",
    "cached_rerank_hybrid": "With the improvement: Haiku picks 5 clauses from the cached corpus → Sonnet + citations",
    "unbounded_sonnet_loop": "Unbounded Sonnet ReAct loop", "bounded_sonnet_cached_gate": "4-step budget + cached SOP + policy gate",
    "hybrid_haiku_sonnet_governed": "Haiku-first, Sonnet on escalation",
    "shared_bus_matched_gate": "Without the lever: shared bus, Sonnet",
    "isolated_cached_gate": "With the lever: isolated + cached, Sonnet",
    "tiered_gate": "With the lever: isolated + cached, Haiku agents + Sonnet patch author",
    "shared_bus_tiered_gate": "Without the lever: shared bus, Haiku agents + Sonnet patch author",
}
UNIT = {"cat1": "item", "cat2": "document", "cat3": "10-turn session", "cat4": "4-question audit", "cat5": "invoice", "cat6": "incident run"}
TITLE = {"cat1": "Classification, extraction & routing", "cat2": "Generative synthesis & drafting", "cat3": "Multi-turn assistants",
         "cat4": "Multi-doc RAG", "cat5": "Process orchestration", "cat6": "Multi-agent swarms"}
BADGE = {"SUPPORTED": "✅ Supported", "PARTLY SUPPORTED": "🟡 Partly", "NOT SUPPORTED": "❌ Not supported", "NOT TESTABLE": "⚪ Not testable"}


def _money(x):
    return "—" if x is None else (f"${x:,.3f}" if x < 1 else f"${x:,.2f}" if x < 100 else f"${x:,.0f}")


def _k(x):
    return "—" if x is None else (f"{x/1e3:,.1f}k" if x >= 1000 else f"{x:,.0f}")


def _cat3_thinking_issue(res):
    cs = res["categories"]["cat3"].get("call_stats")
    if not cs:
        return ("9. **Extended thinking varies output cost (Category 3).** Calls request `thinking={\"type\": \"between_tools\"}`, yet some turns still emit thinking tokens, "
                "which are billed as output; the quality-rerun records were not available to count them.")
    return (f"9. **Extended thinking varies output cost (Category 3).** Calls request `thinking={{\"type\": \"between_tools\"}}`, yet {cs['turn_and_probe_calls_with_thinking']} of "
            f"{cs['turn_and_probe_calls']} turn and probe calls in the quality rerun emitted thinking tokens (up to {cs['max_thinking_tokens']:,} in one call), "
            f"billed as output; {cs['compaction_calls_with_thinking']} of {cs['compaction_calls']} compactions did. The same turn's output cost therefore varies between repeats, "
            "and the per-turn output range above includes thinking.")


CAT5_LABELS = {
    "raw_free_sonnet": "Without the lever, Sonnet (app rung 1)",
    "raw_free_haiku": "Without the lever, Haiku (app rung 4)",
    "bundle_gate_sonnet_cached": "With the lever, Sonnet (app rung 2)",
    "bundle_gate_haiku_escalate": "With the lever, Haiku-first (app rung 3)",
}


CAT1_LABELS = {
    "sonnet_report": "Sonnet 5.5 · without: four-part write-up",
    "sonnet_schema": "Sonnet 5.5 · with: classification + JSON schema",
    "haiku_report": "Haiku 5.5 · without: four-part write-up",
    "haiku_schema": "Haiku 5.5 · with: classification + JSON schema",
}


def _render_cat1(c):
    """Category 1: the deck's lever with and without, by model column (one table)."""
    rungs, q = c["rungs"], c["quality"]
    n = rungs["sonnet_report"]["n"]
    L = [f"### 1. {TITLE['cat1']} (per 1k items, n={n} per cell)", "",
         f"Source: the Category 1 experiment, {c['records']} runs (4 cells × {c['n_items']} items × {c['repeats']} repeats) from "
         f"`backend/experiments/cat1_ablation/runs.jsonl`, selected by the run ids in `{c['summary_source']}`; quality read from the same file. "
         f"Costs are recomputed here from each run's tokens; they match the summary within ${c['max_cost_diff_vs_summary_per_1k']:.4f} per 1k. "
         f"Write-ups ran at max_tokens 8,192, the JSON-schema answers at 512; truncated runs: {sum(c['truncated_runs'].values())}. "
         "The app runs all four cells; its golden replays are repeat 0 of each cell on all 12 items. "
         "Each cell: fields correct (95% Wilson); items fully correct; $ per 1k items (with the improvement: also the Batch API price, computed at 50%, not run); "
         "median prompt / output tokens (output range); median response time.", "",
         "| | " + " | ".join(CAT1_COLS.values()) + " |", "|---|" + "---|" * len(CAT1_COLS)]
    for rk, rl in CAT1_ROWS.items():
        cells = []
        for ck in CAT1_COLS:
            a = CAT1_DESIGN[(rk, ck)]
            v, qa = rungs[a], q[a]
            ci = qa.get("wilson")
            star = "\\*" if not qa.get("given_labels", True) else ""
            batch = rungs.get(f"{a}_batch")
            lat = qa.get("latency_ms_median")
            cells.append(f"{qa['fields']}/{qa['fields_total']}{star}" + (f" ({ci[0]:.0f}–{ci[1]:.0f}%)" if ci else "") + f" fields · {qa['items']}/{qa['items_total']} items · "
                         f"{_money(v['cost_per_1k_billed'])}/1k" + (f" (batch {_money(batch['cost_per_1k_billed'])}, computed)" if batch else "") + " · "
                         f"{_k(v['prompt_tokens_median'])} / {_k(v['output_tokens_median'])} tokens (output {v['output_tokens_range'][0]:,}–{v['output_tokens_range'][1]:,})"
                         + (f" · {lat / 1000:.1f} s" if lat else ""))
        L.append(f"| {rl} | " + " | ".join(cells) + " |")
    wn = c.get("write_up_note") or {}
    amb = wn.get("ambiguous_fields_per_arm") or {}
    L += ["", "\\* The write-up prompt never lists the allowed labels. For the write-ups, \"fields correct\" counts the fields where the reader model could read one "
          "allowed label off the write-up and it was right: whether the write-up is usable as a classification, not the rest of its content. "
          + (f"{amb.get('sonnet_report')} (Sonnet) and {amb.get('haiku_report')} (Haiku) of {c['fields_per_arm']} fields were `ambiguous` "
             f"(several answers, or wording that maps to no single label, e.g. \"{wn.get('example_ambiguous')}\"). " if amb else "")
          + "Ground truth covers 42 fields per repeat (support: queue, priority, action, contains PII; SKU: category, publishing status, contradiction)."]
    if c.get("reader_check_note"):
        L += ["", c["reader_check_note"]]
    if c.get("misses"):
        L += ["", "Where the JSON-schema answers missed (grouped over repeats): "
              + "; ".join(f"{CAT1_LABELS[m['arm_id']].split(' · ')[0]} on {m['item_id']}: {m['field']} {m['returned']!s} instead of {m['expected']!s} "
                          f"({m['runs_missed']}/{m['runs_total']} runs)" for m in c["misses"] if m["arm_id"] in CAT1_LABELS) + "."]
    return L + [""]


def _render_cat2(c):
    """Category 2: without / with the section template, by model column (one table)."""
    rungs, qsrc = c["rungs"], c.get("quality_source") or {}
    cells_q = (c.get("quality") or {}).get("cells") or {}
    h2h = (c.get("quality") or {}).get("h2h") or {}
    trunc = sum((c.get("truncated") or {}).values())
    diff = c.get("max_cost_diff_vs_summary_per_1k")
    mt = qsrc.get("max_tokens") or {}
    L = [f"### 2. {TITLE['cat2']} (per 1k documents, n={c['drafts_per_cell']} drafts per cell)", "",
         f"Source: `backend/experiments/cat2_not_stated/drafts.jsonl`, the latest ok draft per document × model × version × repeat: {c['records']} of "
         f"{c['planned']} planned drafts ({len(c['documents'])} documents × 3 repeats per cell). Costs are recomputed here from each draft's tokens"
         + (f" (within ${diff:.4f} per 1k of the summary)" if diff is not None else "") + ". "
         + (f"Quality from `{qsrc['file']}`: blind judge `{qsrc['judge_model']}` (not one of the models under test), {qsrc['passes']} rubric pass per draft; "
            "key facts from a fixed answer key; action-plan owners and time windows checked against the source. " if qsrc.get("file") else
            f"Quality: not available ({qsrc.get('reason')}). ")
         + (f"Caps: unbounded drafts max_tokens {mt['unbounded']:,}, template drafts {mt['template_not_stated']:,}; " if mt.get("unbounded") and mt.get("template_not_stated") else "")
         + f"truncated drafts: {trunc}. The app's four versions are these four cells; their golden replays are repeat 0 of each cell.", "",
         "Each cell: $ per 1k documents; median prompt / output tokens (output range); grades 1–5 (accuracy / coverage / clarity / actionability / concision); "
         "serious and minor errors per draft; core and detail facts found; numbers not found in the source; action-plan owners and time windows "
         "(in source / not stated / not in source).", "",
         "| | " + " | ".join(CAT2_COLS.values()) + " |", "|---|" + "---|" * len(CAT2_COLS)]
    for rk, rl in CAT2_ROWS.items():
        cells = []
        for ck in CAT2_COLS:
            rung = CAT2_DESIGN[(rk, ck)]
            v, qc = rungs.get(rung), cells_q.get(rung)
            if not v:
                cells.append(f"run pending ({(qc or {}).get('drafts_planned', c['drafts_per_cell'])} drafts planned)")
                continue
            parts = [f"{_money(v['cost_per_1k_billed'])}/1k",
                     f"{_k(v['prompt_tokens_median'])} / {_k(v['output_tokens_median'])} tokens (output {v['output_tokens_range'][0]:,}–{v['output_tokens_range'][1]:,})"]
            if qc and qc.get("rubric") and qc.get("judged_drafts"):
                r = qc["rubric"]
                parts.append("grades " + " / ".join(f"{r[k]:.2f}" for k in CAT2_DIMS)
                             + (f" ({qc['judged_drafts']} of {qc['drafts']} graded)" if qc["judged_drafts"] != qc["drafts"] else ""))
                parts.append(f"serious {qc['serious_per_draft']:.2f} · minor {qc['minor_per_draft']:.2f} per draft")
            elif qc:
                parts.append("not graded yet")
            if qc and qc.get("core_facts"):
                parts.append(f"core facts {_c2_frac(qc['core_facts'])} · detail facts {_c2_frac(qc['detail_facts'])} · numbers not in source {qc.get('not_in_source_numbers', 0)}")
            if qc and qc.get("owner") and qc.get("time_window"):
                o, w = qc["owner"], qc["time_window"]
                parts.append(f"owners {o['supported']} / {o['not_stated']} / {o['unsupported']} · time windows {w['supported']} / {w['not_stated']} / {w['unsupported']}")
            cells.append(" · ".join(parts))
        L.append(f"| {rl} | " + " | ".join(cells) + " |")
    L.append("")
    if h2h.get("status") == "ok" and h2h.get("all"):
        pc = h2h["all"].get("position_consistency") or {}
        L.append("Head-to-head, template vs unbounded on the same document, model and repeat (each pair shown in both orders): all "
                 + _c2_h2h(h2h["all"]) + "; " + "; ".join(f"{CAT2_COLS[m]} {_c2_h2h(b)}" for m, b in (h2h.get("by_model") or {}).items() if b)
                 + f"; position-consistent in {pc.get('consistent', 0)}/{pc.get('pairs', 0)} pairs.")
    else:
        n_pw = ((c.get("quality") or {}).get("counts") or {}).get("pairwise_planned", 48)
        L.append(f"Head-to-head, template vs unbounded on the same document, model and repeat ({n_pw} judge calls): run pending.")
    rg = c["section_regen"]
    if SONNET in rg and HAIKU in rg:
        trunc = sum(rg[m]["truncated"] for m in (SONNET, HAIKU))
        L += ["", f"Single-section regeneration (one call per document x section on each model's repeat-0 template draft, n={rg[SONNET]['n']} per model): "
              f"Sonnet {_money(rg[SONNET]['cost_per_1k'])}/1k edits vs {_money(rg[SONNET]['base_draft_cost_per_1k'])}/1k for the full Sonnet template draft "
              f"(−{pct_saving(rg[SONNET]['base_draft_cost_per_1k'], rg[SONNET]['cost_per_1k']):.0f}%); Haiku {_money(rg[HAIKU]['cost_per_1k'])}/1k edits vs "
              f"{_money(rg[HAIKU]['base_draft_cost_per_1k'])}/1k for the full Haiku template draft (−{pct_saving(rg[HAIKU]['base_draft_cost_per_1k'], rg[HAIKU]['cost_per_1k']):.0f}%); "
              f"{trunc} truncated."]
    else:
        L += ["", f"Single-section regeneration ({c.get('section_regen_planned', 32)} calls: 4 documents x 4 sections on each model's repeat-0 template draft): not captured yet."]
    return L + [""]


def _cat2_regen_sentence(reg):
    """One-section regeneration vs the full template draft it was made on, same model (both models), or ''."""
    if SONNET not in reg or HAIKU not in reg:
        return ""
    parts = [f"{lab} −{pct_saving(reg[m]['base_draft_cost_per_1k'], reg[m]['cost_per_1k']):.0f}% "
             f"({_money(reg[m]['base_draft_cost_per_1k'])} → {_money(reg[m]['cost_per_1k'])}/1k)" for m, lab in ((SONNET, "Sonnet"), (HAIKU, "Haiku"))]
    return (f"one-section regeneration vs the full template draft it was made on, same model: {', '.join(parts)} "
            f"(n={reg[SONNET]['n']} regenerations per model on the {reg[SONNET]['base_drafts']} repeat-0 template drafts)")


def _cat1_unit_sentence(res):
    c = res["categories"]["cat1"]
    if c.get("source") != "ablation":
        return "Category 1 has no experiment data in this run. "
    return (f"Category 1 uses all {c['records']} experiment runs (4 cells × {c['n_items']} items × {c['repeats']} repeats, n={c['records'] // 4} per cell); "
            "its golden replays are repeat 0 of each cell. ")


def _render_cat6(c):
    """Category 6: the deck's lever with and without, by model column (one table)."""
    n = next(iter(c["cpo"].values()))["runs"]
    L = [f"### 6. {TITLE['cat6']} (per incident run, n={n} per cell)", "",
         f"Source: the fair rerun, {c['records']} records (3 incidents × 5 repeats per cell), each patch scored by PR-SANDBOX-GATE-01 "
         "(10 checks). Every cell has the same role instructions, output caps, sandbox gate and one retry; each run starts with a cold cache. "
         "Each cell: verified runs; $ per 1k runs cold / warm; CpO (cost per verified fix) cold / warm; median prompt / output tokens per run; mean model time per run.", "",
         "| | " + " | ".join(CAT6_COLS.values()) + " |", "|---|" + "---|" * len(CAT6_COLS)]
    for rk, rl in CAT6_ROWS.items():
        cells = []
        for ck in CAT6_COLS:
            a = CAT6_DESIGN.get((rk, ck))
            v, s = (c["cpo"].get(a), c["rungs"].get(a)) if a else (None, None)
            if not v:
                cells.append(CAT6_RUN_PENDING)
                continue
            cells.append(f"{v['verified']}/{v['runs']} verified · {_money(v['cost_per_run_cold'] * 1000)} / {_money(v['cost_per_run_warm'] * 1000)} per 1k runs · "
                         f"CpO {_money(v['cpo_cold'])} / {_money(v['cpo_warm'])} · {_k(s['prompt_tokens_median'])} / {_k(s['output_tokens_median'])} tokens · "
                         f"{v['model_s_mean']:.1f} s")
        L.append(f"| {rl} | " + " | ".join(cells) + " |")
    for a in c.get("pending") or []:
        L += ["", f"{CAT6_CELL[a][0].upper()}{CAT6_CELL[a][1:]}: {CAT6_RUN_PENDING} (no runs recorded yet); the claim rows use the "
              f"{len(c['cpo'])} recorded cells."]
    return L + [""]


def _cat6_ceiling_note(res):
    """The Category 6 sentence of the ceiling-effects limit, from the recorded cells ("" when no cell is at the ceiling)."""
    c = (res.get("categories") or {}).get("cat6") or {}
    cells = c.get("cpo") or {}
    if not cells or not all(v["verified"] == v["runs"] for v in cells.values()):
        return ""
    runs = sorted({v["runs"] for v in cells.values()})
    rate = f"{runs[0]}/{runs[0]}" if len(runs) == 1 else "all its runs"
    return (f" Category 6: every {'recorded ' if c.get('pending') else ''}cell verified {rate}, so these incidents are too easy to show a "
            "quality difference with or without the lever, and CpO equals cost per run in every cell.")


CAT5_ROWS = {"without": "Without the lever (free-choice loop over raw ERP tables; on Haiku no escalation path, since only the policy tool can flag one)",
             "with": "With the lever: 4-step budget + deterministic policy tool (also one narrow query and a cached policy manual)"}
CAT5_COLS = {"sonnet": "Sonnet 5.5", "haiku": "Haiku 5.5 (with the lever: Haiku first, Sonnet on escalation)"}
CAT5_DESIGN = {("without", "sonnet"): "raw_free_sonnet", ("without", "haiku"): "raw_free_haiku",
               ("with", "sonnet"): "bundle_gate_sonnet_cached", ("with", "haiku"): "bundle_gate_haiku_escalate"}


def _render_cat5(c):
    """Category 5: the deck's lever with and without, by model column (one table); golden-replay fallback otherwise."""
    rungs = c["rungs"]
    if c.get("source") != "ablation":
        L = [f"### 5. {TITLE['cat5']} (per 1k invoices, n={next(iter(rungs.values()))['n']} per rung)", "",
             f"Source: the Category 5 golden replays ({c.get('reason')}).", "",
             "| Rung | Billed | Warm | Cold | Pre-fix card (billed) | Prompt tok (median) | Output tok (median) |", "|---|---:|---:|---:|---:|---:|---:|"]
        for r, v in rungs.items():
            L.append(f"| {RUNG_LABELS.get(r, r)} | {_money(v['cost_per_1k_billed'])} | {_money(v['cost_per_1k_warm'])} | {_money(v['cost_per_1k_cold'])} | "
                     f"{_money(v['cost_per_1k_billed_repo_card'])} | {_k(v['prompt_tokens_median'])} | {_k(v['output_tokens_median'])} |")
        return L + [""]
    q = c["quality"]
    n_exp = next(iter(q.values()))["expected_runs"]
    L = [f"### 5. {TITLE['cat5']} (per 1k invoices, n={n_exp} per cell)", "",
         f"Source: {c['records']} runs (each cell: {c['invoices_pooled']} invoices × {c['repeats']} repeats"
         + (", some not recorded yet" if c.get("pending_runs") else "") + ") selected by run id from "
         f"`backend/experiments/cat5_ablation/runs.jsonl`; quality from `{c['summary_source']}`. Each voucher is scored field by field against a hand-derived "
         f"answer. Costs are recomputed here from each turn's tokens (within ${c['max_cost_diff_vs_summary_per_1k']:.4f} per 1k of the summary). Every run wrote "
         f"its own cache (per-run nonce), so billed equals cold. Every turn ran at max_tokens {c['settings'].get('max_tokens_per_turn')}. "
         "Each cell: exact vouchers (95% Wilson interval); $ per 1k invoices cold / warm; median prompt / output tokens per invoice; mean model turns; "
         "escalations to Sonnet. The app's four rungs are these four cells; their golden replays are repeat 0 on inv-01..03.", "",
         "| | " + " | ".join(CAT5_COLS.values()) + " |", "|---|" + "---|" * len(CAT5_COLS)]
    for rk, rl in CAT5_ROWS.items():
        cells = []
        for ck in CAT5_COLS:
            a = CAT5_DESIGN.get((rk, ck))
            v, s = (q.get(a), rungs.get(a)) if a else (None, None)
            if not v:
                cells.append("run pending")
                continue
            ci = v["exact_ci"]
            cells.append(f"{v['exact']}/{v['runs']} exact ({ci[0]*100:.0f}–{ci[1]*100:.0f}%)"
                         + (f", {v['pending_runs']} of {v['expected_runs']} runs not recorded yet" if v.get("pending_runs") else "")
                         + f" · {_money(s['cost_per_1k_cold'])} / {_money(s['cost_per_1k_warm'])} per 1k · "
                         f"{_k(s['prompt_tokens_median'])} / {_k(s['output_tokens_median'])} tokens · {v['turns_mean']:.1f} turns"
                         + (f" · escalated {v['escalations']}/{v['runs']}" if a == "bundle_gate_haiku_escalate" else ""))
        L.append(f"| {rl} | " + " | ".join(cells) + " |")
    for a in c.get("pending_cells") or []:
        L += ["", f"{CAT5_LABELS.get(a, a)}: run pending (no runs recorded yet); the scorecard rows use the recorded cells."]
    if c.get("pending_runs"):
        L += ["", f"{c['pending_runs']} runs are not recorded yet (invoices {', '.join(c['pending_invoices'])}); the comparisons in the scorecard use the "
              f"{len(c['common_invoices'])} invoices recorded in every cell."]
    for m in c.get("non_exact_runs") or []:
        L += ["", f"Non-exact run: {CAT5_LABELS.get(m.get('arm_id'), m.get('arm_id'))}, {m.get('preset_id')} repeat {m.get('repeat_index')}: "
              f"fields {', '.join(m.get('mismatched_fields') or [])} differ."]
    return L + [""]


CAT4_LABELS = {
    "naive_full_corpus": "Without the improvement: full corpus, no cache, no citations",
    "cached_rerank_hybrid": "With the improvement: Haiku picks 5 clauses from the cached corpus → Sonnet + citations",
}
CAT4_SCALE_LABEL = {1: "7 docs", 3: "21 docs"}


def _cat4_absence_issue_text():
    """Earlier-design history (the original answer instructions) is in analysis/experiments_log.md (Category 4); nothing to add here."""
    return ""


def _cat4_format_effect_text(c):
    """Earlier-design history (the answer-format change) is in analysis/experiments_log.md (Category 4); nothing to add here."""
    return ""


def _cat4_label(key):
    rung, scale = key.split("|")
    return f"{CAT4_LABELS[rung]} · {CAT4_SCALE_LABEL.get(int(scale), scale)}"


def _cat4_rows(c, table=None):
    """Row keys in display order: corpus 1× then 3×, without then with."""
    have = c["per_question"]
    return [_cat4_key(r, sc) for sc in CAT4_SCALES for r in CAT4_RUNGS if _cat4_key(r, sc) in have]


def _render_cat4(c):
    L = []
    rungs, pq = c["rungs"], c["per_question"]
    stats = c.get("call_stats")
    first = next(iter(rungs.values()))
    if c["source"] == "quality rerun":
        L += [f"### 4. {TITLE['cat4']} (per 1k questions; n={first['n'] * 4} answers per row)", "",
              f"Source: the quality rerun, {stats['records']} records = {stats['answers']} answers (2 versions — without and with the deck's improvement — × 2 corpus "
              "sizes × 3 sessions of 8 questions; each session asked audit-01 then audit-02, so one unit here is a 4-question audit and each session gives two). Corpus "
              "sizes: the app's 7-document deal room, and 21 documents (two synthetic look-alike suppliers added). Every question carried a one-line supplier-scope "
              "prefix. The golden replays are repeat 0 of both versions at 7 documents. Synthesis stop reasons: "
              + ", ".join(f"{k} {v}" for k, v in stats["synthesis_stop_reasons"].items())
              + f"; {stats['synthesis_calls_with_thinking']}/{stats['answers']} answers used extended thinking.", ""]
    else:
        L += [f"### 4. {TITLE['cat4']} (per 1k questions)", "", "Source: the Category 4 golden replays (the quality-rerun records could not be read).", ""]
    L += ["| Version · corpus | Billed | Warm | Cold | Sonnet prompt (median) | Answer output (median) | Citations / answer (median) | Answers with 0 citations | Stop reasons |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for key in _cat4_rows(c):
        v = pq[key]
        cit = "—" if key.startswith("naive") else f"{v['citations_median']:.0f}"
        zero = "—" if key.startswith("naive") else f"{v['questions_with_zero_citations']}/{v['answers']}"
        L.append(f"| {_cat4_label(key)} | {_money(v['cost_per_1k_q_billed'])} | {_money(v['cost_per_1k_q_warm'])} | {_money(v['cost_per_1k_q_cold'])} | "
                 f"{_k(v['synth_prompt_median'])} | {v['synth_output_median']:.0f} | {cit} | {zero} | "
                 + ", ".join(f"{k} {n}" for k, n in sorted(v["stop_reasons"].items())) + " |")
    L += ["", "*Cold* here: the first question of each 4-question audit writes the clause cache (the rerun billed one write per 8-question session). "
          "Cost includes the Haiku clause pick in the version with the improvement; the prompt column is the answering (Sonnet) call.", ""]
    q, src = c.get("quality"), c.get("quality_source") or {}
    if q:
        L += [f"Answer quality (read from `{src['file']}`, keys version `{src.get('keys_version')}`; {src.get('answers')} answers, {src.get('judged')} graded by a blind "
              f"grader (`{src.get('judge_model')}`, not a model under test, {src.get('judge_passes')} pass per answer); deterministic answer-key measures; 95% Wilson intervals):", "",
              "| Version · corpus | Key facts stated | Citations at expected clauses | Expected clauses cited | Expected clauses among Haiku's picks | Other suppliers' clauses picked | "
              "Grader correctness (1–5) | Grader completeness (1–5) | Answers with a serious error | Contaminated answers |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]

        def qm(m):
            if not m or not m.get("total"):
                return "—"
            ci = f" ({m['ci_low']*100:.0f}–{m['ci_high']*100:.0f}%)" if m.get("ci_low") is not None else ""
            return f"{m['hits']}/{m['total']} = {m['hits']/m['total']*100:.0f}%{ci}"
        for key in _cat4_rows(c):
            v = q.get(key)
            if not v:
                continue
            L.append(f"| {_cat4_label(key)} | {qm(v['fact_recall'])} | {qm(v['citations_at_expected'])} | {qm(v['expected_chunk_recall'])} | {qm(v['recall_after_rerank'])} | "
                     f"{qm(v['distractors_selected'])} | {v['correctness_mean']:.2f} | {v['completeness_mean']:.2f} | {qm(v['answers_with_material_error'])} | {qm(v['contaminated_answers'])} |")
        L += ["", "*Key facts*: fixed answer key (4–7 facts per question), deterministic matching. *Expected clauses among Haiku's picks*: the clauses the answer key "
              "needs that are among the 5 Haiku picked (the version without the improvement sends every clause: —). "
              "*Serious error*: a statement the grader marked material (wrong amount, party, date, condition or precedence, or a claim that the documents lack something they contain). "
              "*Contaminated*: states another supplier's value for a keyed fact or cites another supplier's clause.", ""]
    else:
        L += [f"Answer quality: not available ({src.get('reason')}).", ""]
    return L


def _cat5_unit_sentence(res):
    c = res["categories"]["cat5"]
    if c.get("source") != "ablation":
        return "Category 5 uses its golden replays (n=3 per rung; the experiment records could not be read). "
    n_exp = next(iter(c["quality"].values()))["expected_runs"]
    pend_cells = c.get("pending_cells") or []
    return (f"Category 5 uses the {c['records']} recorded runs of its with/without design on Sonnet and Haiku (4 cells × {c['invoices_pooled']} invoices × "
            f"{c['repeats']} repeats, n={n_exp} per cell" + (f"; {c['pending_runs']} not recorded yet" if c.get("pending_runs") else "")
            + ("; " + ", ".join(CAT5_LABELS[a].split(' (')[0] for a in pend_cells) + ": run pending" if pend_cells else "")
            + "); its golden replays are repeat 0 of each cell on inv-01..03. ")


def _cat5_issues(res):
    """Category 5 has no open issue in the lab code or data; earlier runs and fixes are recorded in the experiments log."""
    return []


def _trace_store_sentence(dd):
    """Short factual statement of what backend/traces/ holds (files and distinct runs per category)."""
    t = dd["totals"]
    per = "; ".join(f"{cat} {b['raw_traces']} files / {b['canonical_runs']} runs" for cat, b in dd["by_category"].items())
    modes = ", ".join(f"{m} {n}" for m, n in sorted(t["raw_by_mode"].items()))
    return (f"`backend/traces/` holds {t['raw_traces']} trace files ({modes}), {t['canonical_runs']} distinct runs of the current golden replays"
            + (f" ({per})" if per else "") + ". The figures below are computed from the experiment records and golden replays, not from the traces. "
            "Replay requests do not write traces; `_backups/` is not read.")


def _cat2_unit_sentence(res):
    c = res["categories"].get("cat2") or {}
    if not c.get("rungs"):
        return "Category 2 has no experiment drafts in this run. "
    pend = c.get("pending_rungs") or []
    return (f"Category 2 uses the latest ok experiment draft per document × model × version × repeat ({c['records']} of {c['planned']} planned, "
            f"n={c['drafts_per_cell']} per cell" + (f"; {len(pend)} cells pending" if pend else "") + "); its golden replays are repeat 0 of each cell. ")


def _strip_number(text):
    return re.sub(r"^\d+\.\s+", "", text)


def _cat5_ceiling_note(res):
    """Category 5's ceiling line, from the recorded cells (a pending cell is named, not assumed)."""
    c = res["categories"].get("cat5") or {}
    q = c.get("quality") or {}
    head = "**Ceiling effects.** Category 5: "
    tail = "; the invoices test simple arithmetic (quantities × rates, a GST split, a debit note)."
    if not q:
        return head + "no recorded cells to judge" + tail
    shares = {a: v["exact"] / v["runs"] for a, v in q.items() if v.get("runs")}
    pend = [CAT5_LABELS.get(a, a).split(" (")[0] for a in c.get("pending_cells") or []]
    pend_txt = (" (" + ", ".join(pend) + ": run pending)") if pend else ""
    if shares and min(shares.values()) >= 0.9:
        return (head + f"every recorded cell scored at or near 100% exact vouchers{pend_txt}, so accuracy differences between those cells "
                "cannot be detected" + tail)
    return (head + "exact-voucher shares per recorded cell: " + "; ".join(
        f"{CAT5_LABELS.get(a, a).split(' (')[0]} {q[a]['exact']}/{q[a]['runs']}" for a in shares) + pend_txt + tail)


def _known_limits(res):
    """One de-duplicated, present-tense list: limits of the data, the measurements and the app as they stand."""
    classes = ((res.get("dedup") or {}).get("totals") or {}).get("classes") or {}
    err = classes.get("error (live, no tokens)", 0)
    return [
        "**Small samples.** Category 1 has 12 items (36 runs per cell: 12 items × 3 repeats); Category 2 has 4 documents (12 drafts per cell: 4 × 3 repeats); "
        "Category 3 has 6 sessions per version (2 scenarios × 3 repeats); Category 4 has 24 answers per version and corpus size (8 questions × 3 sessions); "
        "Category 5 has 12 invoices (36 runs per cell: 12 invoices × 3 repeats); Category 6 has 15 runs per cell (3 incidents × 5 repeats). "
        "Treat percentages as indicative, not statistically robust.",
        "**One reader or judge, one pass.** Category 1 write-ups are read by one reader model (`claude-opus-5-5`, not a model under test) in one pass; "
        "it read all 100 known fields of 20 JSON answers rewritten as plain text correctly, but no second reader or human cross-checks it. "
        "Category 2 drafts are graded by one blind judge (`claude-opus-5-5`, not a model under test): one rubric pass per draft and head-to-head comparisons shown in "
        "both orders, plus a deterministic fact key; no second judge or human grading cross-checks the judge's taste. "
        "Category 4 answers get one blind-grader pass each (`claude-opus-5-5`) plus a deterministic answer key; grader noise is not measured and no human graded the answers.",
        "**Category 1 ground truth covers 42 fields per repeat** (4 per ticket, 3 per SKU); the other schema fields (reason code, PII categories, hazmat class, material) "
        "are not scored. The write-up prompt never lists the allowed labels, so a write-up's score counts whether one allowed label can be read off it (usable as a "
        "classification), not the rest of its content. Half the items (the six batch items) are short, so pooled token ranges mix two item sizes.",
        "**Category 2 owner and time-window check.** A name or date counts as in the source when it occurs there; the check does not test that the source assigns "
        "that action to that owner or date (the judge's errors cover attribution).",
        "**Category 3 quality** is a fixed answer key scored by deterministic string matching (no LLM judge). It checks whether specific IDs, amounts and dates "
        "survive, not whether an answer is helpful; the recall questions are 6 per scenario (12 in all), each asked once per session.",
        _strip_number(_cat3_thinking_issue(res)).replace(" in the quality rerun ", " in the experiment ").replace("the quality-rerun records", "the experiment records"),
        "**Category 4 corpus and retrieval.** 8 questions on one deal room; the larger corpus adds two synthetic look-alike suppliers generated by a deterministic "
        "transform of Deccan's documents, not real contracts. The clause boundaries and headings Haiku picks from were written for these documents and the "
        "clause-pick prompt names the kinds of clause the questions ask about, so the share of needed clauses among its picks may be lower for unseen questions.",
        "**Levers changed together.** Category 1's with-design asks for the classification instead of a write-up and enforces the JSON schema in one step, so the "
        "saving cannot be split between the two. Category 5's with-design changes the step budget, the policy tool, the data access (one narrow query) and caching "
        "together, so its saving cannot be split between them.",
        _cat5_ceiling_note(res) + _cat6_ceiling_note(res),
        "**Cache warming across rungs.** In captures where rungs and items ran in sequence, later calls can read caches written by earlier ones; the *billed* "
        "column includes this and the *cold* column removes it. Each Category 6 run writes its own cache (a per-run nonce in the cached prefix).",
        "**Trace `finops` is modelled, not billed, for multi-step rollups.** The Category 5 and 6 session rollups store a modelled cold-cache cost "
        "(`_compute_step_cold_warm`), not the cache tokens the API returned. `summarize_traces()` averages every trace file per partition without de-duplication. "
        "This report recomputes every cost from the recorded tokens instead."
        + (f" {err} live error traces hold zero tokens and are excluded." if err else ""),
        "**Scale claims.** The deck's daily-volume claim (Category 6: 1.5M–10M tokens/dev/day) and its production-scale framing can't be checked from single runs.",
    ]


def render_markdown(res):
    L = []
    dd = res["dedup"]["totals"]
    verdicts = Counter(c["verdict"] for c in res["claims"])
    L += [
        "# Six AI Archetypes deck: claims checked against the NovaMart traces",
        "",
        "_Generated by `backend/scripts/validate_deck_claims.py` from the Category 1 experiment (`backend/experiments/cat1_ablation/runs.jsonl` + "
        "`backend/replays/cat1_ablation_summary.json`), the Category 2 experiment (`backend/experiments/cat2_not_stated/drafts.jsonl` + "
        "`backend/replays/cat2_quality_summary.json`, section regeneration from `backend/experiments/cat2_not_stated/section_regens.jsonl`), the Category 3 quality rerun "
        "(`backend/experiments/cat3_quality/runs.jsonl` + `backend/replays/cat3_quality_summary.json`), the Category 4 quality rerun "
        "(`backend/experiments/cat4_quality/runs.jsonl` + `backend/replays/cat4_quality_summary.json`), the Category 5 ablation "
        "(`backend/experiments/cat5_ablation/runs.jsonl` + `backend/replays/cat5_ablation_summary.json`), the Category 6 fair rerun "
        "(`backend/experiments/cat6_fair_rerun/runs.jsonl`) and `backend/traces/`. Re-run the script after new runs._",
        "",
        NEUTRAL_NOTE,
        "",
        "## Trace store",
        "",
        _trace_store_sentence(res["dedup"]),
        "",
    ]
    L += [
        "**Unit of analysis:** each category's experiment records; the golden replays the app serves are repeat 0 of each cell. "
        + _cat1_unit_sentence(res) + _cat2_unit_sentence(res) + "Category 3 uses the 12 quality-rerun records of its without/with design (2 versions × 2 sessions × 3 repeats, n=6 per version); its golden replays are repeat 0 of both. "
        "Category 4 uses the 12 quality-rerun sessions of its without/with design (2 versions × 2 corpus sizes × 3 sessions of 8 questions, 96 answers, n=24 per row); "
        "its golden replays are repeat 0 of both versions at the 7-document corpus. "
        + _cat5_unit_sentence(res) +
        "Category 6 uses the 45 fair-rerun records of its with/without design (3 cells × 3 incidents × 5 repeats, n=15 per cell); its golden replays are repeat 0 of each cell. "
        "Costs are recomputed per API call from recorded token counts, priced by the model that served the call. "
        "The traces' own `finops` blocks are not used, so the results don't depend on how the app priced them.",
        "",
        "**Cost views.** *Billed*: cache tokens exactly as the API reported them during capture. "
        "*Warm*: every cached-prefix token is a cache read (steady state). "
        "*Cold*: the first call per model in each unit writes the prefix. "
        "All dollar figures use Anthropic's published rates (the rate card in `backend/app/core/pricing.py`).",
        "",
        "## Scorecard",
        "",
        " · ".join(f"{BADGE[k]}: **{verdicts.get(k, 0)}**" for k in BADGE),
        "",
        "Verdict rule: **Supported** means the measurement falls inside the claimed range or clears the threshold. "
        "**Partly** means the direction holds but the magnitude is outside the range, or a confound limits the conclusion. "
        "**Not supported** means the data contradicts the claim. " + IMPLICIT_RULE,
        "",
        "| Archetype | Deck claim | Measured (canonical runs) | Verdict | Note |",
        "|---|---|---|---|---|",
    ]
    for c in res["claims"]:
        L.append(f"| {c['category']} | {c['claim']} | {c['measured']} | {BADGE[c['verdict']]} | {c['note']} |")

    L += ["", "## Cost per 1,000 units by rung", ""]
    for cat in ("cat1", "cat2", "cat3", "cat4", "cat5", "cat6"):
        if cat == "cat4":
            L += _render_cat4(res["categories"]["cat4"])
            continue
        if cat == "cat5":
            L += _render_cat5(res["categories"]["cat5"])
            continue
        if cat == "cat6":
            L += _render_cat6(res["categories"]["cat6"])
            continue
        if cat == "cat2":
            L += _render_cat2(res["categories"]["cat2"])
            continue
        if cat == "cat1":
            c1_ = res["categories"]["cat1"]
            L += (_render_cat1(c1_) if c1_.get("source") == "ablation"
                  else [f"### 1. {TITLE['cat1']}", "", f"Not available: {c1_.get('reason')}.", ""])
            continue
        rungs = res["categories"][cat]["rungs"]
        first = next(iter(rungs.values()))
        L += [f"### {cat[-1]}. {TITLE[cat]} (per 1k {UNIT[cat]}s, n={first['n']} per rung)", "",
              "| Rung | Billed | vs first rung | Warm | Cold | Prompt tok (median) | Output tok (median) | Output share of cost |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
        base = first["cost_per_1k_billed"]
        for r, v in rungs.items():
            if "n" not in v:
                L.append(f"| {RUNG_LABELS.get(r, r)} | {_money(v['cost_per_1k_billed'])} | −{pct_saving(base, v['cost_per_1k_billed']):.1f}% | | | | | |")
                continue
            sv = pct_saving(base, v["cost_per_1k_billed"])
            L.append(f"| {RUNG_LABELS.get(r, r)} | {_money(v['cost_per_1k_billed'])} | {'—' if r == next(iter(rungs)) else f'−{sv:.1f}%'} | "
                     f"{_money(v['cost_per_1k_warm'])} | {_money(v['cost_per_1k_cold'])} | "
                     f"{_k(v['prompt_tokens_median'])} | {_k(v['output_tokens_median'])} | {v['output_cost_share_median']*100:.0f}% |")
        L.append("")
        c = res["categories"][cat]
        if cat == "cat3":
            if c["source"] == "quality rerun":
                L += [f"Source: the quality rerun, {c['records']} records (2 versions — without and with the deck's improvement — × 2 sessions × 3 repeats). Costs cover "
                      "turns 1–10 and the compactions before them; the recall-probe phase is excluded. The golden replays are repeat 0 of both versions.", ""]
            else:
                L += ["Source: the Category 3 golden replays (the quality-rerun records could not be read).", ""]
            L += ["Context per turn (prompt tokens, mean per session):", "",
                  "| Version | Turn 1 | Turn 3 | Turn 6 | Turn 10 | Slope (tok/turn) | Peak context | Compactor calls / session |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
            for r, gr in c["context_growth"].items():
                L.append(f"| {RUNG_LABELS[r]} | {_k(gr['turn1'])} | {_k(gr['turn3'])} | {_k(gr['turn6'])} | {_k(gr['turn10'])} | +{gr['slope_tokens_per_turn']:,.0f} | {_k(gr['peak_context'])} | {gr['compactor_calls_per_session']:.0f} |")
            L.append("| *Deck illustration* | *1.2k* | *6.5k* | *14k* | *25k+* | *~+2.6k* | | |")
            L.append("")
            q, qsrc = c["quality"], c["quality_source"]
            if q:
                L += [f"Answer quality (fixed answer key, keys version `{qsrc.get('keys_version')}`, read from `{qsrc['file']}`; 95% Wilson intervals):", "",
                      "| Version | Sessions | Answers grounded (turns 1–9) | Final-summary details | …from turns 1–3 | …from turns 4–6 | …from turns 7–9 | Recall questions answered |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|"]

                def qm(m):
                    if not m:
                        return "—"
                    ci = f" ({m['ci_low']*100:.0f}–{m['ci_high']*100:.0f}%)" if m.get("ci_low") is not None else ""
                    return f"{m['hits']}/{m['total']} = {m['hits']/m['total']*100:.1f}%{ci}"
                for r in rungs:
                    v = q.get(r)
                    if not v:
                        continue
                    lb = v["ledger_by_origin"]
                    L.append(f"| {RUNG_LABELS[r]} | {v['runs']} | {qm(v['turn_recall'])} | {qm(v['ledger_recall'])} | {qm(lb.get('1-3'))} | {qm(lb.get('4-6'))} | {qm(lb.get('7-9'))} | {qm(v['probe_accuracy'])} |")
                L += ["", "*Answers grounded*: key facts the reply to each of turns 1–9 should contain. *Final-summary details*: facts from turns 1–9 that the turn-10 "
                      "consolidated ledger should repeat, split by the turn they came from. *Recall questions*: six short questions per session, asked after turn 10, "
                      "each about one detail stated once in an early turn."]
            else:
                L.append(f"Answer quality: not available ({qsrc['reason']}).")
        L.append("")

    L += ["## Token scale across archetypes (median total tokens per unit, deck-typical rung)", "", "| Unit | Tokens |", "|---|---:|"]
    L += [f"| {k} | {_k(v)} |" for k, v in res["scale"].items()]
    L += ["", "## Pricing check", "",
          "| Rate ($/MTok) | `pricing.py` | Anthropic published | Note |", "|---|---:|---:|---|",
          "| Sonnet 5.5 input / output | 2.00 / 10.00 | 2.00 / 10.00 | — |",
          "| Sonnet 5.5 cache write (5-min) / cache read | 2.50 / 0.10 | 2.50 (1.25× input, assumed) / 0.10 | — |",
          "| Haiku 5.5 input / output | 0.10 / 0.50 | 0.10 / 0.50 (≤100K prompt) | Prompts above 100K tokens cost 0.50 / 2.50; not modelled, and no recorded Haiku call exceeds 100K "
          f"({res['haiku_calls_over_100k_prompt']} found) |",
          "| Haiku 5.5 cache write (5-min) / cache read | 0.125 / 0.01 | 0.125 (1.25× input, assumed) / 0.01 | — |",
          "| Message Batches API | 50% of the rates above | 50% | Used only for the computed Batch API prices in Category 1; no batch was run |",
          "",
          "## Known limits of the current data and app",
          "",
          *[f"{n}. {t}" for n, t in enumerate(_known_limits(res), 1)],
          ""]
    return "\n".join(L)


def write_outputs(res):
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "deck_claims_validation.json").write_text(json.dumps(res, indent=2, default=str))
    (OUT_DIR / "deck_claims_validation.md").write_text(render_markdown(res))


if __name__ == "__main__":
    r = analyse()
    write_outputs(r)
    dd = r["dedup"]["totals"]
    print(f"traces {dd['raw_traces']} -> {dd['distinct_fingerprints']} fingerprints -> {dd['canonical_runs']} canonical runs :: {dd['classes']}")
    for c in r["claims"]:
        print(f"[{c['verdict']:>16}] {c['category']:<14} {c['claim']}\n{'':>19}{c['measured']}\n{'':>19}{c['note']}")
    print(f"\nwrote {OUT_DIR / 'deck_claims_validation.md'} and .json")
