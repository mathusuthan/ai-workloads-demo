"""De-duplicated validation of the "6 Key Production AI Archetypes" deck claims.

Reads these sources and writes a JSON + Markdown report:

1. backend/traces/            -> de-duplication audit (how many traces are distinct runs)
2. backend/replays/*.json     -> the canonical dataset for Categories 1, 2 and 5: one record per (item x rung),
                                 with per-call token counts and the model that served each call
3. backend/experiments/cat3_quality/runs.jsonl (read-only) + backend/replays/cat3_quality_summary.json
                                 (fallback analysis/cat3_quality_rerun.json)
                              -> Category 3: all quality-rerun records (3 rungs x 2 sessions x 3 repeats) for
                                 cost and context growth; answer-key quality scores from the summary
                                 (falls back to the Category 3 golden replays if the rerun file is missing)
4. backend/replays/cat2_quality_summary.json (fallback analysis/cat2_quality.json)
                              -> Category 2: blind LLM-judge quality of the 12 stored drafts (rubric, serious errors,
                                 head-to-head preference) and the deterministic fact key
   backend/replays/cat2_not_stated_summary.json (fallback analysis/cat2_not_stated.json)
                              -> Category 2 follow-up: the template plus one "Not stated in source" sentence, 48 fresh
                                 drafts (shown beside the app's template; it is not the app's template)
5. backend/experiments/cat4_quality/runs.jsonl (read-only) + backend/replays/cat4_quality_summary.json
                                 (fallback analysis/cat4_quality_rerun.json)
                              -> Category 4: all quality-rerun records (4 rungs x 2 corpus sizes x 3 sessions of
                                 8 questions = 192 answers) for cost and tokens; answer-key and blind-grader quality
                                 and the break-even tables from the summary (falls back to the golden replays)
6. backend/experiments/cat6_fair_rerun/runs.jsonl (read-only) + analysis/cat6_fair_rerun.json
                              -> Category 6: all fair-rerun records (4 arms x 3 incidents x 5 repeats);
                                 verdicts from the summary's `rescored` section (current sandbox),
                                 falling back to the as-recorded verdicts in the JSONL

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
CAT2_QUALITY_ANALYSIS = OUT_DIR / "cat2_quality.json"
CAT2_FIX_SUMMARY = REPLAYS / "cat2_not_stated_summary.json"
CAT2_FIX_ANALYSIS = OUT_DIR / "cat2_not_stated.json"
CAT2_FIX_ARMS = ["template_original", "template_not_stated"]
CAT2_DIMS = ["factual_accuracy", "coverage", "clarity", "actionability", "concision"]
CAT2_VERDICTS = ["derived_correct", "derived_incorrect", "not_in_source_unverifiable", "not_a_claim", "no_majority"]
CAT4_RERUN = BACKEND / "experiments" / "cat4_quality" / "runs.jsonl"
CAT4_QUALITY_SUMMARY = REPLAYS / "cat4_quality_summary.json"
CAT4_QUALITY_ANALYSIS = OUT_DIR / "cat4_quality_rerun.json"
CAT4_SYNTH_MAX_TOKENS = 4096  # records at another synthesis cap are superseded (the 2,048-cap pilot)
CAT4_APP_MAX_TOKENS_BEFORE = 2048
CAT4_RUNGS = ["naive_full_corpus", "cached_full_corpus_citations", "hybrid_rag_rerank_citations", "cached_rerank_hybrid"]
CAT4_SCALES = [1, 3]
CAT6_RERUN = BACKEND / "experiments" / "cat6_fair_rerun" / "runs.jsonl"
CAT6_RERUN_SUMMARY = OUT_DIR / "cat6_fair_rerun.json"
CAT6_ARMS = ["shared_bus_original", "shared_bus_matched_gate", "isolated_cached_gate", "tiered_gate"]

SONNET, HAIKU, GEMINI = "claude-sonnet-5-5", "claude-haiku-5-5", "gemini-decision-1"

# $/1M tokens: (input, output, cache_write_5m, cache_read)
RATE_CARDS = {
    # backend/app/core/pricing.py before the 2026-11-21 fix (Sonnet cache read $0.20), kept for comparison
    "repo": {
        SONNET: (2.00, 10.00, 2.50, 0.20),
        HAIKU: (0.10, 0.50, 0.125, 0.01),
        GEMINI: (0.10, 0.00, 0.00, 0.00),
    },
    # Anthropic published pricing (model table cached 2026-11-03): Sonnet 5.5 $2/$10,
    # cache reads $0.10; Haiku 5.5 $0.10/$0.50 for prompts <=100K tokens.
    # Cache writes assumed at the standard 1.25x input (5-minute TTL); Haiku cache read 0.1x.
    # Gemini Decision 1 is not an Anthropic model; its rate is kept from the repo (unverified).
    "official": {
        SONNET: (2.00, 10.00, 2.50, 0.10),
        HAIKU: (0.10, 0.50, 0.125, 0.01),
        GEMINI: (0.10, 0.00, 0.00, 0.00),
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
def dedup_audit():
    recs = []
    for p in TRACES.rglob("*.json"):
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
        "max_duplicates_of_one_run": max(len(v) for v in groups.values()),
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
    recs = [json.loads(p.read_text()) for p in TRACES.rglob("*.json")]
    current = current_seed_trace_ids(recs)
    return {_seed_slot(r): r for r in recs if r.get("trace_id") in current}


# ------------------------------------------------------------- 2. canonical units
def cat1_units(seeds):
    d = load(1)
    acc_key = {
        "sonnet_naive": (SONNET, "naive_chatbot"),
        "haiku_naive": (HAIKU, "naive_unconstrained_prose"),
        "haiku_calibrated": (HAIKU, "strict_json_schema"),
        "gemini_decision": (GEMINI, "system1_decisions_api"),
    }
    units = defaultdict(list)
    items = {}
    for iid, p in d["presets"].items():
        items[iid] = {r: call(v["model_id"], v["input_tokens"], v["output_tokens"]) for r, v in p["rungs"].items()}
    for iid, b in d["batch_items"].items():
        items[iid] = {
            "sonnet_naive": call(SONNET, b["sonnet_input_tokens"], b["sonnet_output_tokens"]),
            "haiku_naive": call(HAIKU, b["haiku_naive_input_tokens"], b["haiku_naive_output_tokens"]),
            "haiku_calibrated": call(HAIKU, b["input_tokens"], b["haiku_output_tokens"]),
            "gemini_decision": call(GEMINI, b["gemini_input_tokens"], 0),
        }
    for iid, rungs in items.items():
        for rung, c in rungs.items():
            m, pat = acc_key[rung]
            s = seeds.get(("cat1_classification_routing", m, pat, iid))
            a = (s or {}).get("extra_metadata", {}).get("accuracy", {})
            units[rung].append({
                "item": iid, "calls": [c],
                "quality": {"schema_valid": a.get("schema_valid"), "matched": a.get("matched_count"), "fields": a.get("total_fields")},
                "hit_max_tokens": c["out"] >= 2048,
            })
    return units


def cat2_units():
    d = load(2)
    units = defaultdict(list)
    for iid, p in d["presets"].items():
        for rung, v in p["rungs"].items():
            units[rung].append({"item": iid, "calls": [call(v["model_id"], v["input_tokens"], v["output_tokens"])], "stop_reason": v.get("stop_reason")})
    regens = defaultdict(list)  # model -> list of {item, section, call}
    for iid, secs in d["section_regens"].items():
        for sec, by_model in secs.items():
            for model, v in by_model.items():
                regens[model].append({"item": iid, "section": sec, "call": call(model, v["input_tokens"], v["output_tokens"])})
    return units, regens


def cat3_rerun_records():
    """Latest ok quality-rerun record per (rung, session, repeat); the JSONL is only read. None if absent."""
    try:
        lines = CAT3_RERUN.read_text().splitlines()
    except OSError:
        return None
    latest = {}
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") == "ok":
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


def _c2_count(m):
    return {"hits": m["hits"], "total": m["total"]}


def cat2_quality():
    """Per-rung blind-judge + fact-key quality: (rung -> measures, source info) or (None, reason)."""
    try:
        d = json.loads(CAT2_QUALITY_SUMMARY.read_text())
        rungs = {r["rung_id"]: {"drafts": r["drafts"], "core": _c2_count(r["core_facts"]), "detail": _c2_count(r["detail_facts"]),
                                "rubric": {k: r["rubric"][k]["mean"] for k in CAT2_DIMS}, "serious": r["serious_errors"], "minor": r["minor_errors"],
                                "not_in_source": r["numbers"]["not_in_source"], "verdicts": {k: r["numbers"]["verdicts"].get(k, 0) for k in CAT2_VERDICTS},
                                "h2h": {o: dict(v) for o, v in r["head_to_head"].items()}, "action_items": r.get("action_items"),
                                "cost_per_1k": r.get("cost_per_1k_docs_usd")} for r in d["rungs"]}
        pc = d["pairwise"]["overall"]["position_consistency"]
        return rungs, {"file": "backend/replays/cat2_quality_summary.json", "keys_version": d.get("keys_version"), "judge_model": d["judge_model"],
                       "passes": d["passes_per_draft"], "drafts_per_cell": d["drafts_per_cell"], "documents": len(d["documents"]), "calls": d["calls"],
                       "position_consistency": [pc["consistent"], pc["pairs"]]}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT2_QUALITY_ANALYSIS.read_text())
        det, j = d["deterministic"], d["judge"]
        wins = j["pairwise"]["overall"]["wins"]
        ties = j["pairwise"]["overall"]["ties"]
        rungs = {}
        for rid, v in det["rungs"].items():
            h2h = {}
            for o in det["rungs"]:
                if o == rid:
                    continue
                t = ties.get(f"{rid}|{o}", ties.get(f"{o}|{rid}", 0))
                h2h[o] = {"wins": wins[rid][o], "losses": wins[o][rid], "ties": t}
            rungs[rid] = {"drafts": v["drafts"], "core": _c2_count(v["coverage"]["core"]), "detail": _c2_count(v["coverage"]["detail"]),
                          "rubric": {k: j["rubric"]["rungs"][rid][k]["mean"] for k in CAT2_DIMS},
                          "serious": j["errors"]["rungs"][rid]["material"], "minor": j["errors"]["rungs"][rid]["minor"],
                          "not_in_source": v["numbers"]["not_in_source"],
                          "verdicts": {k: j["numbers"]["rungs"][rid]["majority_counts"].get(k, 0) for k in CAT2_VERDICTS},
                          "h2h": h2h, "action_items": None, "cost_per_1k": v.get("cost_per_1k_docs_usd")}
        pc = j["pairwise"]["overall"]["position_consistency"]
        dq = j["data_quality"]
        return rungs, {"file": "analysis/cat2_quality.json", "keys_version": det.get("keys_version"), "judge_model": j["model_requested"],
                       "passes": 3, "drafts_per_cell": 1, "documents": len(det["preset_ids"]),
                       "calls": {"ok": dq["ok_calls"], "error_records": dq["error_records"]},
                       "position_consistency": [pc["consistent"], pc["pairs_with_both_orders"]]}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, {"file": None, "reason": "neither backend/replays/cat2_quality_summary.json nor analysis/cat2_quality.json could be read"}


def cat2_fix():
    """Category 2 follow-up ("Not stated in source" sentence): (normalised data, source info) or (None, reason)."""
    def cell_out(arm, m, drafts, items, owner, window, serious, rubric, cost, detail):
        return {"arm": arm, "model": m, "drafts": drafts, "items": items, "owner": owner, "window": window, "serious": serious,
                "rubric": rubric, "cost_per_1k": cost, "detail": detail}
    try:
        d = json.loads(CAT2_FIX_SUMMARY.read_text())
        cells = {(c["arm"], c["model_key"]): cell_out(c["arm"], c["model_key"], c["drafts"], c["action_items"], c["owner"], c["time_window"],
                                                      c["serious_per_draft"], c["rubric"], c["cost_per_1k_docs_usd"], c["detail_facts"]) for c in d["cells"]}
        h2h = {k: {dim: d["head_to_head"][k]["all"][dim] for dim in ("overall", "accuracy", "usefulness_to_reader")} | {"calls": d["head_to_head"][k]["all"]["calls"]}
               for k in ("vs_original", "vs_unbounded")}
        return {"cells": cells, "h2h": h2h, "added_instruction": d["added_instruction"]}, {
            "file": "backend/replays/cat2_not_stated_summary.json", "drafts": d["counts"]["drafts"], "per_cell": d["counts"]["drafts_per_document_model_template"],
            "judge_calls": d["counts"]["judge_ok_calls"], "judge_model": d["judge_model"], "passes": d["judge_passes_per_draft"]}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT2_FIX_ANALYSIS.read_text())
        cells = {}
        for g in d["groups"].values():
            cells[(g["arm"], g["model_key"])] = cell_out(g["arm"], g["model_key"], g["drafts"], g["action_items"], g["owner"], g["time_window"],
                                                         g["serious_per_draft"]["mean"], {k: v["mean"] for k, v in g["rubric"].items()},
                                                         g["cost_per_1k_docs_usd"]["mean"], g["detail_facts"])
        def rec(b):
            return {dim: {"wins": b[dim]["not_stated_wins"], "losses": b[dim]["other_wins"], "ties": b[dim]["ties"]} for dim in ("overall", "accuracy", "usefulness_to_reader")} | {"calls": b["calls"]}
        h2h = {"vs_original": rec(d["pairwise"]["matched"]["all"]), "vs_unbounded": rec(d["pairwise"]["vs_unbounded"]["all"])}
        return {"cells": cells, "h2h": h2h, "added_instruction": d["design"]["added_instruction"]}, {
            "file": "analysis/cat2_not_stated.json", "drafts": d["drafts_data_quality"]["ok_drafts"], "per_cell": d["design"]["repeats"],
            "judge_calls": d["judge_data_quality"]["ok_calls"], "judge_model": d["design"]["judge_model"], "passes": d["design"]["judge_passes_per_draft"]}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, {"file": None, "reason": "neither backend/replays/cat2_not_stated_summary.json nor analysis/cat2_not_stated.json could be read"}


def _cat2_fix_sentence(f2):
    """One sentence on the follow-up for the implicit-row note and Issue 12 (empty when absent)."""
    if not f2:
        return ""
    c = {(k if isinstance(k, tuple) else tuple(k.split("|"))): v for k, v in f2["cells"].items()}
    o = [c[("template_original", m)] for m in ("sonnet", "haiku")]
    n = [c[("template_not_stated", m)] for m in ("sonnet", "haiku")]
    ub = f2["h2h"]["vs_unbounded"]
    return (f" Follow-up (not the app's template): one added sentence letting the template write \"Not stated in source\" cut serious errors per draft from "
            f"{o[0]['serious']:.2f} / {o[1]['serious']:.2f} to {n[0]['serious']:.2f} / {n[1]['serious']:.2f} (Sonnet / Haiku, {n[0]['drafts']} fresh drafts each) "
            f"and raised accuracy from {o[0]['rubric']['factual_accuracy']:.2f} / {o[1]['rubric']['factual_accuracy']:.2f} to "
            f"{n[0]['rubric']['factual_accuracy']:.2f} / {n[1]['rubric']['factual_accuracy']:.2f}, but actionability fell "
            f"({o[0]['rubric']['actionability']:.2f} / {o[1]['rubric']['actionability']:.2f} → {n[0]['rubric']['actionability']:.2f} / {n[1]['rubric']['actionability']:.2f}) "
            f"and the long draft is still preferred in {ub['overall']['losses']} of {ub['calls']} comparisons.")


def cat3_quality():
    """Per-rung answer-key scores: (rung -> measures, source file label) or (None, reason)."""
    try:
        d = json.loads(CAT3_QUALITY_SUMMARY.read_text())
        rungs = {r["rung_id"]: {"runs": r["runs"], "turn_recall": _measure(r["turn_recall"]), "ledger_recall": _measure(r["ledger_recall"]),
                                "ledger_by_origin": {k: _measure(v) for k, v in (r.get("ledger_by_origin") or {}).items()},
                                "probe_accuracy": _measure(r["probe_accuracy"])} for r in d["rungs"]}
        return rungs, {"file": "backend/replays/cat3_quality_summary.json", "keys_version": d.get("keys_version"), "runs": d.get("runs")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT3_QUALITY_ANALYSIS.read_text())
        rungs = {}
        for rid, v in d["rerun"]["rungs"].items():
            q = v["quality"]
            rungs[rid] = {"runs": q.get("sessions") or v["cost"]["runs"], "turn_recall": _measure(q["turn_recall"]["turns_1_9"]),
                          "ledger_recall": _measure(q["ledger_recall"]["overall"]),
                          "ledger_by_origin": {k.replace("origin_", "").replace("_", "-"): _measure(m) for k, m in (q["ledger_recall"].get("by_origin") or {}).items()},
                          "probe_accuracy": _measure(q["probe_accuracy"]["overall"])}
        return rungs, {"file": "analysis/cat3_quality_rerun.json", "keys_version": d.get("keys_version"), "runs": d["rerun"].get("ok_runs_used")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, {"file": None, "reason": "neither backend/replays/cat3_quality_summary.json nor analysis/cat3_quality_rerun.json could be read"}


def cat4_rerun_records():
    """Latest ok quality-rerun record per (rung, scale, repeat) at the current synthesis cap; None if absent."""
    try:
        lines = CAT4_RERUN.read_text().splitlines()
    except OSError:
        return None
    latest = {}
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") == "ok" and (r.get("settings") or {}).get("synth_max_tokens") == CAT4_SYNTH_MAX_TOKENS:
            latest[(r["rung_id"], int(r["scale"]), int(r["repeat_index"]))] = r
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
                calls, per_q = [], []
                for q in qs:
                    qc = [call(q["model_id"], q["input_tokens"], q["output_tokens"], q["cache_creation_tokens"], q["cache_read_tokens"], role="synthesis")]
                    if q.get("reranker_model_id"):
                        qc.append(call(q["reranker_model_id"], q["reranker_input_tokens"], q["reranker_output_tokens"], role="rerank"))
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
                     "value_contaminated_unattributed_answers", "exposure_answers", "recall_after_bm25", "recall_after_rerank",
                     "distractors_selected", "judged", "correctness_mean", "completeness_mean", "material_errors",
                     "answers_with_material_error")


def cat4_quality():
    """(cells keyed 'rung|scale', break-even tables by scale, source) or (None, None, reason)."""
    try:
        d = json.loads(CAT4_QUALITY_SUMMARY.read_text())
        cells = {_cat4_key(c["rung_id"], c["scale"]): {k: c.get(k) for k in _CAT4_CELL_FIELDS} for c in d["cells"]}
        return cells, d["break_even"], {"file": "backend/replays/cat4_quality_summary.json", "keys_version": d.get("keys_version"),
                                        "judge_model": d.get("judge_model"), "judge_passes": d.get("judge_passes"),
                                        "answers": d.get("answers_scored"), "judged": d.get("answers_judged"),
                                        "sessions_per_cell": d.get("sessions_per_cell"), "corpus": d.get("corpus")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        d = json.loads(CAT4_QUALITY_ANALYSIS.read_text())
        cells = {}
        for key, g in d["rerun"]["groups"].items():
            ret, j = g.get("retrieval") or {}, g.get("judge") or {}
            cells[key] = {
                "answers": g["answers"], "fact_recall": g["fact_recall"], "fact_recall_supplier_specific": g["fact_recall_supplier_specific"],
                "citations_per_answer_mean": g["citations_per_answer_mean"], "zero_citation_answers": g["zero_citation_answers"],
                "expected_chunk_recall": g["expected_chunk_recall"], "citations_at_expected": g["citations_at_expected"],
                "cited_support": g["cited_support"], "contaminated_answers": g["contaminated_answers"],
                "value_contaminated_unattributed_answers": g.get("value_contaminated_unattributed_answers"),
                "exposure_answers": g.get("answers_whose_synthesis_saw_distractor_text"),
                "recall_after_bm25": ret.get("recall_after_bm25"), "recall_after_rerank": ret.get("recall_after_rerank"),
                "distractors_selected": ret.get("distractors_selected"), "judged": j.get("judgements") or 0,
                "correctness_mean": j.get("correctness_mean"), "completeness_mean": j.get("completeness_mean"),
                "material_errors": j.get("material_errors"), "answers_with_material_error": j.get("answers_with_material_error"),
            }
        be = {k: v for k, v in d["rerun"]["break_even"].items()}
        return cells, be, {"file": "analysis/cat4_quality_rerun.json", "keys_version": d.get("keys_version"), "judge_model": None,
                           "judge_passes": 1, "answers": sum(c["answers"] for c in cells.values()),
                           "judged": sum(c["judged"] for c in cells.values()), "sessions_per_cell": None, "corpus": d.get("corpus")}
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None, None, {"file": None, "reason": "neither backend/replays/cat4_quality_summary.json nor analysis/cat4_quality_rerun.json could be read"}


def cat5_units(seeds):
    d = load(5)
    pat = {"unbounded_sonnet_loop": "unbounded_uncached_react_loop", "bounded_sonnet_cached_gate": "bounded_sonnet_cached_gate",
           "hybrid_haiku_sonnet_governed": "hybrid_haiku_sonnet_governed_loop"}
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


def cat6_verdict_overrides():
    """(arm, preset, repeat, attempt) -> re-scored sandbox verdict, from analysis/cat6_fair_rerun.json."""
    try:
        summary = json.loads(CAT6_RERUN_SUMMARY.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    rs = summary.get("rescored")
    if not rs:
        return None
    return {(c["arm_id"], c["preset_id"], int(c["repeat_index"]), c["attempt"]):
            {"passed": c["rescored_passed_checks"], "checks": c["rescored_total_checks"], "verified": bool(c["rescored_verified"])}
            for c in rs.get("changes") or []}


def cat6_units():
    overrides = cat6_verdict_overrides()
    units = defaultdict(list)
    for r in cat6_rerun_records():
        key = (r["arm_id"], r["preset_id"], int(r["repeat_index"]))
        calls = [call(t["model_id"], t["input_tokens"], t["output_tokens"], t["cache_creation_tokens"], t["cache_read_tokens"], role=t["agent_role"])
                 for t in r["turns"]]

        def verdict_of(attempt):
            sb = (r.get(attempt) or {}).get("sandbox") or {}
            v = {"passed": sb.get("passed_checks"), "checks": sb.get("total_checks"), "verified": bool(sb.get("verified_outcome"))}
            return (overrides or {}).get((*key, attempt), v)

        fin, first = verdict_of("final"), verdict_of("first_attempt")
        units[r["arm_id"]].append({
            "item": f"{r['preset_id']}/r{r['repeat_index']}", "calls": calls,
            "verified": fin["verified"], "passed": fin["passed"], "checks": fin["checks"], "first_verified": first["verified"],
            "retries": int(r.get("retries_used") or 0),
            "turns_at_max_tokens": sum(1 for t in r["turns"] if t.get("stop_reason") == "max_tokens"),
            "turn1_prefix": calls[0]["cw"] + calls[0]["cr"],
        })
    return units, ("rescored" if overrides is not None else "as recorded")


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


def analyse():
    seeds = seed_index()
    res = {"dedup": dedup_audit(), "categories": {}, "claims": [], "pricing_notes": []}
    claims = res["claims"]

    def claim(cat, text, measured, v, note=""):
        claims.append({"category": cat, "claim": text, "measured": measured, "verdict": v, "note": note})

    # ---------------- Cat 1
    u1 = cat1_units(seeds)
    order1 = ["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"]
    s1 = summarize_rungs(u1, order1)
    batch = st.mean(unit_cost(u["calls"], batch=True) for u in u1["haiku_calibrated"]) * 1000
    s1["haiku_calibrated_batch"] = {"cost_per_1k_billed": batch}
    acc1 = {r: {"exact_items": sum(1 for u in u1[r] if u["quality"]["matched"] == u["quality"]["fields"]),
                "fields_matched": sum(u["quality"]["matched"] or 0 for u in u1[r]),
                "fields_total": sum(u["quality"]["fields"] or 0 for u in u1[r]),
                "schema_valid": sum(1 for u in u1[r] if u["quality"]["schema_valid"])} for r in order1}
    trunc1 = {r: sum(1 for u in u1[r] if u["hit_max_tokens"]) for r in ("sonnet_naive", "haiku_naive")}
    res["categories"]["cat1"] = {"rungs": s1, "accuracy": acc1, "naive_runs_hitting_max_tokens_2048": trunc1, "n_items": len(u1["sonnet_naive"])}
    hc = s1["haiku_calibrated"]
    payload_in = [u["calls"][0]["in"] for u in u1["gemini_decision"]]
    claim("Cat 1", "Input 500–1,500 tokens", f"payload {min(payload_in):,}–{max(payload_in):,} (Gemini, payload only); Haiku+schema prompt {hc['prompt_tokens_range'][0]:,}–{hc['prompt_tokens_range'][1]:,}",
          verdict(False, True), "Raw payloads sit in band; adding a schema + system prompt pushes the real prompt to ~0.9–2.1k.")
    claim("Cat 1", "Output 10–100 tokens", f"Haiku+schema output {hc['output_tokens_range'][0]}–{hc['output_tokens_range'][1]} (median {hc['output_tokens_median']:.0f})",
          verdict(False, True), "Schema output lands at ~70–135 tokens: at or just over the top of the band.")
    claim("Cat 1", "Input:output ≈ 20:1 to 50:1", f"Haiku+schema median {hc['io_ratio_median']:.0f}:1", verdict(20 <= hc["io_ratio_median"] <= 50, True),
          "Input-heavy as claimed, but below the 20:1 floor because schema output is ~100 tokens, not 10–50.")
    best = min(s1["haiku_calibrated"]["cost_per_1k_billed"], s1["gemini_decision"]["cost_per_1k_billed"])
    sav = pct_saving(s1["sonnet_naive"]["cost_per_1k_billed"], s1["haiku_calibrated"]["cost_per_1k_billed"])
    sav_same_model = pct_saving(s1["haiku_naive"]["cost_per_1k_billed"], s1["haiku_calibrated"]["cost_per_1k_billed"])
    claim("Cat 1", "Small model + strict JSON schema + batching cuts unit cost by >80%",
          f"Sonnet prose → Haiku schema −{sav:.1f}%; Haiku prose → Haiku schema (schema alone) −{sav_same_model:.1f}%; + batch ${batch:.3f}/1k",
          verdict(sav > 80), f"A conservative figure: {trunc1['sonnet_naive']}/12 Sonnet prose runs hit max_tokens=2048, so the uncapped naive cost would be higher. Even the schema alone, on the same model, clears 80%.")
    a_s, a_h, a_g = acc1["sonnet_naive"], acc1["haiku_calibrated"], acc1["gemini_decision"]
    claim("Cat 1", "…without losing accuracy (implicit)",
          f"fields correct: Sonnet prose {a_s['fields_matched']}/{a_s['fields_total']}, Haiku schema {a_h['fields_matched']}/{a_h['fields_total']}, Gemini {a_g['fields_matched']}/{a_g['fields_total']}; exact items {a_s['exact_items']} / {a_h['exact_items']} / {a_g['exact_items']} of 12",
          verdict(True), "The cheaper rungs are also more accurate. Prose was scored by text matching, which is generous to it.")

    # ---------------- Cat 2
    u2, regens = cat2_units()
    order2 = ["sonnet_unbounded", "sonnet_templated", "haiku_templated"]
    s2 = summarize_rungs(u2, order2)
    reg = {m: {"n": len(v), "cost_per_1k": st.mean(call_cost(x["call"]) for x in v) * 1000,
               "output_median": med([x["call"]["out"] for x in v]), "input_median": med([x["call"]["in"] for x in v])} for m, v in regens.items()}
    hybrid_flow = st.mean(unit_cost(u["calls"]) for u in u2["haiku_templated"]) * 1000 + reg[SONNET]["cost_per_1k"]
    q2, q2_source = cat2_quality()
    f2, f2_source = cat2_fix()
    res["categories"]["cat2"] = {"rungs": s2, "section_regen": reg, "haiku_draft_plus_1_sonnet_section_regen_per_1k": hybrid_flow,
                                 "quality": q2, "quality_source": q2_source,
                                 "template_fix": ({**f2, "cells": {f"{a}|{m}": v for (a, m), v in f2["cells"].items()}} if f2 else None),
                                 "template_fix_source": f2_source}
    ub = s2["sonnet_unbounded"]
    claim("Cat 2", "Input 1,500–4,000 tokens", f"unbounded {ub['prompt_tokens_range'][0]:,}–{ub['prompt_tokens_range'][1]:,}; templated {s2['sonnet_templated']['prompt_tokens_range'][0]:,}–{s2['sonnet_templated']['prompt_tokens_range'][1]:,}",
          verdict(False, True), "In band without the template; the section template adds ~1.2k prompt tokens.")
    claim("Cat 2", "Output 800–3,000+ tokens", f"unbounded {ub['output_tokens_range'][0]:,}–{ub['output_tokens_range'][1]:,}; templated {s2['sonnet_templated']['output_tokens_range'][0]:,}–{s2['sonnet_templated']['output_tokens_range'][1]:,}", verdict(True))
    claim("Cat 2", "Input:output ≈ 1:1 to 1:2 and output-dominated cost", f"unbounded in:out ≈ 1:{1/ub['io_ratio_median']:.2f}, output = {ub['output_cost_share_median']*100:.0f}% of cost; templated {s2['sonnet_templated']['output_cost_share_median']*100:.0f}%",
          verdict(ub["output_cost_share_median"] > 0.5), "")
    claim("Cat 2", "Output tokens cost 3–5× input", "Sonnet 5.5 and Haiku 5.5 output is exactly 5× input", verdict(True))
    sv2 = pct_saving(ub["cost_per_1k_billed"], s2["sonnet_templated"]["cost_per_1k_billed"])
    sv2h = pct_saving(ub["cost_per_1k_billed"], s2["haiku_templated"]["cost_per_1k_billed"])
    if q2:
        qu, qt, qh = q2["sonnet_unbounded"], q2["sonnet_templated"], q2["haiku_templated"]
        lever_note2 = (f"The cost claim holds, but the saving is not free: graded blind, the templated drafts score lower on accuracy "
                       f"({qu['rubric']['factual_accuracy']:.2f} → {qt['rubric']['factual_accuracy']:.2f} / {qh['rubric']['factual_accuracy']:.2f}) and have more serious errors "
                       f"({qu['serious']} → {qt['serious']} / {qh['serious']}); see the quality table and the implicit-claim row.")
    else:
        lever_note2 = f"Savings are cost-only: no draft-quality data could be read ({q2_source['reason']})."
    claim("Cat 2", "Section templates + length bounds control output cost", f"same model (Sonnet): −{sv2:.0f}%; + Haiku: −{sv2h:.0f}%; 1-section regen vs full re-draft: −{pct_saving(s2['sonnet_templated']['cost_per_1k_billed'], reg[SONNET]['cost_per_1k']):.0f}%",
          verdict(True), lever_note2)
    if q2:
        templ = [("Sonnet template", qt), ("Haiku template", qh)]
        t_wins = sum(q["h2h"]["sonnet_unbounded"]["wins"] for _, q in templ)
        t_ties = sum(q["h2h"]["sonnet_unbounded"]["ties"] for _, q in templ)
        t_n = sum(sum(q["h2h"]["sonnet_unbounded"].values()) for _, q in templ)
        lo, hi = wilson(t_wins, t_n)
        pref_worse = hi is not None and hi < 0.5  # templated win share clearly below even (Wilson upper bound < 50%)
        err_worse = all(q["serious"] > qu["serious"] for _, q in templ)
        acc_worse = all(q["rubric"]["factual_accuracy"] < qu["rubric"]["factual_accuracy"] for _, q in templ)
        cov_worse = all(q["rubric"]["coverage"] < qu["rubric"]["coverage"] for _, q in templ)
        fr = lambda m: f"{m['hits']}/{m['total']}"  # noqa: E731
        g = lambda q, k: f"{q['rubric'][k]:.2f}"  # noqa: E731
        ai = [q["action_items"] for _, q in templ if q.get("action_items")]
        ai_txt = (f" The template requires an owner and a time window for every action item; the grader flagged an owner or deadline the source does not support in "
                  f"{sum(a['flagged'] for a in ai)} of {sum(a['total'] for a in ai)} templated action items ({sum(a['flagged_serious'] for a in ai)} with a serious error).") if ai else ""
        pc = q2_source["position_consistency"]
        claim("Cat 2", "…without losing draft quality (implicit)",
              f"head-to-head: templated drafts preferred over the unbounded draft in {t_wins}/{t_n} comparisons ({t_ties} ties; 95% Wilson {lo*100:.0f}–{hi*100:.0f}%); "
              f"accuracy {g(qu, 'factual_accuracy')} unbounded vs {g(qt, 'factual_accuracy')} / {g(qh, 'factual_accuracy')} (Sonnet / Haiku template), "
              f"coverage {g(qu, 'coverage')} vs {g(qt, 'coverage')} / {g(qh, 'coverage')}; serious errors {qu['serious']} vs {qt['serious']} / {qh['serious']}. "
              f"Not worse: core facts {fr(qu['core'])} vs {fr(qt['core'])} / {fr(qh['core'])}. Better: clarity {g(qu, 'clarity')} vs {g(qt, 'clarity')} / {g(qh, 'clarity')}, "
              f"concision {g(qu, 'concision')} vs {g(qt, 'concision')} / {g(qh, 'concision')}",
              verdict(not (pref_worse or err_worse or acc_worse or cov_worse), not pref_worse),
              f"Blind LLM judge (`{q2_source['judge_model']}`, not one of the models under test; {q2_source['passes']} rubric passes per draft; every pair shown in both orders, "
              f"position-consistent in {pc[0]}/{pc[1]} pairs), one draft per rung × {q2_source['documents']} documents; the lead verified the serious errors against the source payloads. "
              "Shorter drafts keep every core fact and read better, but they are less accurate and less complete and lose every head-to-head comparison."
              + ai_txt + " A single judge may favour longer drafts (its prompt tells it to ignore length and layout), but the serious errors were verified against the sources, so they do not rest on the judge's taste."
              + _cat2_fix_sentence(f2) + (" This row grades the template as the app ships it." if f2 else ""))
    else:
        claim("Cat 2", "…without losing draft quality (implicit)", "no quality data", "NOT TESTABLE", q2_source["reason"])
    claim("Tiers 1–2 rule", "60–80% lower unit inference cost (Cat 1 & 2)", f"Cat 1 −{sav:.0f}%, Cat 2 −{sv2:.0f}% (template only) to −{sv2h:.0f}% (template + Haiku)",
          verdict(False, True), f"Outside the range on both sides: changing the model as well gives ~98–99% (more than claimed); templating alone on the same model gives {sv2:.0f}% (less).")

    # ---------------- Cat 3 (quality rerun: 3 rungs x 2 sessions x 3 repeats)
    u3, cat3_source, cat3_stats = cat3_units()
    order3 = ["naive_full_history", "prefix_cached_history", "prefix_cached_summarized"]
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
    prefix3 = med([u["calls"][0]["cw"] + u["calls"][0]["cr"] for u in u3["prefix_cached_history"]])
    res["categories"]["cat3"] = {"rungs": s3, "context_growth": growth, "source": cat3_source, "records": sum(len(u3[r]) for r in order3),
                                 "call_stats": cat3_stats, "quality": q3, "quality_source": q3_source, "handbook_prefix_tokens": prefix3,
                                 "turn_output": {"turns": len(all_turns3), "in_150_600": in_band, "median": med([x["output"] for x in all_turns3]),
                                                 "range": rng([x["output"] for x in all_turns3]), "turns_with_thinking": len(with_thinking)}}
    g = growth["naive_full_history"]
    n3 = s3["naive_full_history"]["n"]
    claim("Cat 3", "Per-turn context grows 1.2k → 6.5k → 14k → 25k+ (turns 1/3/6/10)", f"naive (mean of n={n3}): {g['turn1']/1e3:.1f}k → {g['turn3']/1e3:.1f}k → {g['turn6']/1e3:.1f}k → {g['turn10']/1e3:.1f}k",
          verdict(False, True), f"Starts much higher (a ~{prefix3/1e3:.1f}k-token handbook is sent on every turn) and grows more slowly: +{g['slope_tokens_per_turn']/1e3:.1f}k/turn vs the ~2.6k/turn the chart implies.")
    claim("Cat 3", "Session 10,000–40,000+ tokens", f"peak context {g['peak_context']/1e3:.1f}k; cumulative billed prompt per session {s3['naive_full_history']['prompt_tokens_median']/1e3:.0f}k (median, n={n3})",
          verdict(False, True), f"Holds for context-window size. Billed tokens per 10-turn session are ~{s3['naive_full_history']['prompt_tokens_median']/40e3:.0f}× the top of the range, because every turn re-sends the history.")
    to3 = res["categories"]["cat3"]["turn_output"]
    out_med_ok = 150 <= to3["median"] <= 600
    claim("Cat 3", "Output 150–600 tokens per turn",
          f"all rungs: median {to3['median']:.0f}, range {to3['range'][0]:,}–{to3['range'][1]:,}; {in_band}/{to3['turns']} turns in 150–600",
          verdict(to3["range"][1] <= 600 and to3["range"][0] >= 150, out_med_ok),
          f"Output tokens include extended thinking, which was non-zero on {to3['turns_with_thinking']}/{to3['turns']} turns, so the same turn varies a lot between repeats. "
          + ("The typical turn is in range; the longest replies are several times the top of it." if out_med_ok else "The typical turn is outside the range."))
    gs, gc = growth["prefix_cached_summarized"], growth["prefix_cached_history"]
    cut_s = pct_saving(s3["naive_full_history"]["cost_per_1k_billed"], s3["prefix_cached_summarized"]["cost_per_1k_billed"])
    cut_c = pct_saving(s3["naive_full_history"]["cost_per_1k_billed"], s3["prefix_cached_history"]["cost_per_1k_billed"])
    lever_measured = (f"context slope: naive +{g['slope_tokens_per_turn']:.0f} tok/turn → summarized +{gs['slope_tokens_per_turn']:.0f} tok/turn (peak {gs['peak_context']/1e3:.1f}k); "
                      f"cost −{cut_s:.0f}% billed (n={n3} sessions per rung)")
    lever_note = (f"Caching alone cuts cost −{cut_c:.0f}% but context still grows +{gc['slope_tokens_per_turn']:.0f} tok/turn (quadratic session total). "
                  "Only summarization bounds the growth.")
    if q3:
        qs_, qc_ = q3["prefix_cached_summarized"], q3["prefix_cached_history"]
        es, ec = qs_["ledger_by_origin"].get("1-3"), qc_["ledger_by_origin"].get("1-3")
        fr = lambda m: f"{m['hits']}/{m['total']}"  # noqa: E731
        lever_measured += (f"; quality trade-off: recall questions {fr(qs_['probe_accuracy'])} vs {fr(qc_['probe_accuracy'])} with cached full history, "
                           f"turn 1–3 details kept in the final summary {fr(es)} vs {fr(ec)}")
        lever_note += (" The cost claim holds, but the saving is not free: compaction drops early-turn specifics, which the assistant then "
                       "declines to recall (see the quality table and the implicit-claim row).")
    else:
        lever_note += f" No answer-quality data could be read ({q3_source['reason']})."
    claim("Cat 3", "Prefix caching + sliding-window summary prevents quadratic session cost", lever_measured, verdict(True), lever_note)
    if q3:
        def worse(a, b):  # a clearly below b: Wilson intervals do not overlap
            return a and b and a["ci_high"] is not None and b["ci_low"] is not None and a["ci_high"] < b["ci_low"]
        probe_worse = worse(qs_["probe_accuracy"], qc_["probe_accuracy"])
        ledger_worse = worse(es, ec)
        grounded_worse = worse(qs_["turn_recall"], qc_["turn_recall"])
        claim("Cat 3", "…without losing answer quality (implicit)",
              f"answers grounded (turns 1–9): {fr(qs_['turn_recall'])} summarized vs {fr(qc_['turn_recall'])} cached full history; "
              f"recall questions {fr(qs_['probe_accuracy'])} vs {fr(qc_['probe_accuracy'])}; turn 1–3 details in final summary {fr(es)} vs {fr(ec)}",
              verdict(not (probe_worse or ledger_worse or grounded_worse), ledger_worse and not probe_worse),
              "Answer key, deterministic string matching, 95% Wilson intervals. Replies on turns 1–9 stay grounded on every rung, but once early turns are "
              "compacted the assistant can no longer recall their specifics and the final summary keeps fewer of them. Caching alone changes no quality measure.")
    else:
        claim("Cat 3", "…without losing answer quality (implicit)", "no quality data", "NOT TESTABLE", q3_source["reason"])

    # ---------------- Cat 4 (quality rerun: 4 rungs x 2 corpus scales x 3 sessions of 8 questions)
    u4, cat4_source, cat4_stats = cat4_units()
    order4 = [_cat4_key(r, sc) for r in CAT4_RUNGS for sc in CAT4_SCALES if u4.get(_cat4_key(r, sc))]
    s4 = summarize_rungs(u4, order4)
    per_q = {}
    for key in order4:
        qs = [q for u in u4[key] for q in u["per_question"]]
        synth = [q["calls"][-1] for q in qs]  # synthesis is the last call of each question
        per_q[key] = {
            "answers": len(qs),
            "synth_prompt_range": rng([prompt_tokens(c) for c in synth]),
            "synth_prompt_median": med([prompt_tokens(c) for c in synth]),
            "synth_output_range": rng([c["out"] for c in synth]),
            "synth_output_median": med([c["out"] for c in synth]),
            "synth_outputs": [c["out"] for c in synth],
            "io_ratio_median": med([prompt_tokens(c) / c["out"] for c in synth if c["out"]]),
            "cost_per_1k_q_billed": s4[key]["cost_per_1k_billed"] / 4,
            "cost_per_1k_q_warm": s4[key]["cost_per_1k_warm"] / 4,
            "cost_per_1k_q_cold": s4[key]["cost_per_1k_cold"] / 4,
            "cost_per_1k_q_billed_repo_card": s4[key]["cost_per_1k_billed_repo_card"] / 4,
            "citations_median": med([q["citations"] for q in qs]),
            "questions_with_zero_citations": sum(1 for q in qs if q["citations"] == 0),
            "stop_reasons": dict(Counter(str(q["stop_reason"]) for q in qs)),
        }
    q4, be4, q4_source = cat4_quality()
    res["categories"]["cat4"] = {"rungs": s4, "per_question": per_q, "source": cat4_source, "call_stats": cat4_stats,
                                 "quality": q4, "break_even": be4, "quality_source": q4_source}
    K = _cat4_key
    fr4 = lambda m: f"{m['hits']}/{m['total']}" if m else "—"  # noqa: E731
    pc4 = lambda m: f"{m['hits'] / m['total'] * 100:.0f}%" if m and m["total"] else "—"  # noqa: E731
    have3 = all(K(r, 3) in per_q for r in CAT4_RUNGS[:3])
    nq1 = per_q[K("naive_full_corpus", 1)]
    nq3 = per_q.get(K("naive_full_corpus", 3))
    hq1 = per_q[K("hybrid_rag_rerank_citations", 1)]
    full_rows = [per_q[k] for k in (K("naive_full_corpus", 1), K("naive_full_corpus", 3), K("cached_full_corpus_citations", 1), K("cached_full_corpus_citations", 3)) if k in per_q]
    full_lo = min(r["synth_prompt_range"][0] for r in full_rows)
    full_hi = max(r["synth_prompt_range"][1] for r in full_rows)
    claim("Cat 4", "Input 15k–100k+ tokens",
          f"full corpus {full_lo/1e3:.1f}k–{full_hi/1e3:.1f}k per question (7 documents → 21 documents); retrieval {hq1['synth_prompt_range'][0]/1e3:.1f}k–{hq1['synth_prompt_range'][1]/1e3:.1f}k synthesis prompt",
          verdict(full_lo >= 15_000 and full_hi <= 100_000),
          f"n={sum(r['answers'] for r in per_q.values())} answers. Every full-corpus prompt is in the band at both corpus sizes; retrieval cuts the answering model's prompt below it by design.")
    outs = [o for r in per_q.values() for o in r["synth_outputs"]]
    in_band = sum(1 for o in outs if 400 <= o <= 1500)
    out_med = med(outs)
    claim("Cat 4", "Output 400–1,500 tokens",
          f"all {len(outs)} answers: median {out_med:.0f}, range {min(outs):,}–{max(outs):,}; {in_band}/{len(outs)} in 400–1,500",
          verdict(min(outs) >= 400 and max(outs) <= 1500, 400 <= out_med <= 1500),
          "Output tokens include extended thinking. "
          + (f"{cat4_stats['synthesis_outputs_above_app_cap_before']} answers used more than the app's former 2,048-token cap (now 4,096). " if cat4_stats else ""))
    r3 = nq3["io_ratio_median"] if nq3 else None
    claim("Cat 4", "Input:output ≈ 20:1 to 100:1",
          f"full-corpus median {nq1['io_ratio_median']:.1f}:1 (7 documents)" + (f", {r3:.1f}:1 (21 documents)" if r3 else ""),
          verdict(all(x is not None and 20 <= x <= 100 for x in (nq1["io_ratio_median"], r3)), any(x is not None and 20 <= x <= 100 for x in (nq1["io_ratio_median"], r3))),
          "Grows with the corpus: at the 7-document deal room it sits at the 20:1 floor; at 3× it is inside the range.")
    # lever row: judged on the combined rung (cached full-corpus rerank -> 5 chunks -> synthesis), which was run
    paired = q4 and K("cached_rerank_hybrid", 3) in (q4 or {}) and have3
    if paired:
        c1, c3 = q4[K("cached_full_corpus_citations", 1)], q4[K("cached_full_corpus_citations", 3)]
        h1, h3 = q4[K("hybrid_rag_rerank_citations", 1)], q4[K("hybrid_rag_rerank_citations", 3)]
        p1, p3 = q4[K("cached_rerank_hybrid", 1)], q4[K("cached_rerank_hybrid", 3)]
        cost = lambda r, sc, v="billed": per_q[K(r, sc)][f"cost_per_1k_q_{v}"] / 1000  # noqa: E731
        be3 = {(r["a"], r["b"]): r for r in (be4 or {}).get("3", [])}
        be1 = {(r["a"], r["b"]): r for r in (be4 or {}).get("1", [])}
        b_cp3, b_cp1 = be3.get(("cached_full_corpus_citations", "cached_rerank_hybrid")), be1.get(("cached_full_corpus_citations", "cached_rerank_hybrid"))

        def worse(a, b):  # a clearly above b: Wilson intervals do not overlap
            return bool(a and b and a.get("ci_low") is not None and b.get("ci_high") is not None and a["ci_low"] > b["ci_high"])
        q_worse = worse(p3["answers_with_material_error"], c3["answers_with_material_error"])
        measured = (f"paired rung (Haiku picks 5 clauses from the cached full corpus, Sonnet answers over them; n=24 per corpus size): "
                    f"expected clauses kept {pc4(p1['recall_after_rerank'])} / {pc4(p3['recall_after_rerank'])} (7 / 21 documents) vs BM25+rerank "
                    f"{pc4(h1['recall_after_rerank'])} / {pc4(h3['recall_after_rerank'])}; other suppliers' clauses selected {fr4(p3['distractors_selected'])} vs {fr4(h3['distractors_selected'])}; "
                    f"$/question billed ${cost('cached_rerank_hybrid', 1):.4f} / ${cost('cached_rerank_hybrid', 3):.4f} vs BM25+rerank ${cost('hybrid_rag_rerank_citations', 1):.4f} / "
                    f"${cost('hybrid_rag_rerank_citations', 3):.4f} and cached full corpus ${cost('cached_full_corpus_citations', 1):.4f} / ${cost('cached_full_corpus_citations', 3):.4f}; "
                    f"grader correctness {p1['correctness_mean']:.2f} / {p3['correctness_mean']:.2f} vs cached full corpus {c1['correctness_mean']:.2f} / {c3['correctness_mean']:.2f}; "
                    f"answers with a serious error {fr4(p1['answers_with_material_error'])} / {fr4(p3['answers_with_material_error'])} vs {fr4(c1['answers_with_material_error'])} / {fr4(c3['answers_with_material_error'])}")
        note = ("Pairing works on retrieval and cost: reranking over the cached corpus finds every expected clause at both corpus sizes, picks no other supplier's clause, and is "
                "the cheapest version per question billed in 8-question sessions. It does not match the cached full corpus on answer quality: with 5 clauses the answering "
                f"model sometimes states that the documents contain no gate or term that is in a clause it was not sent{' (serious-error rate clearly higher at 21 documents, Wilson intervals do not overlap)' if q_worse else ''}. "
                + (f"Warm, the cached full corpus is cheaper per question; it overtakes the paired rung once {b_cp1['questions']} (7 documents) / {b_cp3['questions']} (21 documents) questions share one cache write. "
                   if b_cp1 and b_cp3 and b_cp1.get("questions") and b_cp3.get("questions") else "")
                + "Verdict: cost and retrieval hold; quality does not hold against the version without retrieval.")
        claim("Cat 4", "Pair hybrid retrieval (reranking + chunk filtering) with context caching", measured, verdict(False, True), note)
        # implicit quality row
        n1, n3q = q4[K("naive_full_corpus", 1)], q4[K("naive_full_corpus", 3)]
        cache_loss = worse(c1["answers_with_material_error"], n1["answers_with_material_error"]) or worse(c3["answers_with_material_error"], n3q["answers_with_material_error"])
        retr_loss = {(r, sc): worse(q4[K(r, sc)]["answers_with_material_error"], q4[K("cached_full_corpus_citations", sc)]["answers_with_material_error"])
                     for r in ("hybrid_rag_rerank_citations", "cached_rerank_hybrid") for sc in CAT4_SCALES}
        any_retr_loss = any(retr_loss.values())
        claim("Cat 4", "…without losing answer quality (implicit)",
              f"answers with a serious error (7 / 21 documents, n=24 each): naive {fr4(n1['answers_with_material_error'])} / {fr4(n3q['answers_with_material_error'])}, "
              f"cached full corpus {fr4(c1['answers_with_material_error'])} / {fr4(c3['answers_with_material_error'])}, BM25+rerank {fr4(h1['answers_with_material_error'])} / {fr4(h3['answers_with_material_error'])}, "
              f"paired {fr4(p1['answers_with_material_error'])} / {fr4(p3['answers_with_material_error'])}; grader correctness naive {n1['correctness_mean']:.2f} / {n3q['correctness_mean']:.2f}, "
              f"cached {c1['correctness_mean']:.2f} / {c3['correctness_mean']:.2f}, BM25+rerank {h1['correctness_mean']:.2f} / {h3['correctness_mean']:.2f}, paired {p1['correctness_mean']:.2f} / {p3['correctness_mean']:.2f}; "
              f"key facts BM25+rerank {fr4(h1['fact_recall'])} / {fr4(h3['fact_recall'])} vs cached {fr4(c1['fact_recall'])} / {fr4(c3['fact_recall'])}",
              verdict(not cache_loss and not any_retr_loss, not cache_loss),
              "Rule: a lever loses quality when its share of answers with a serious error is clearly higher (95% Wilson intervals do not overlap) than the full-corpus "
              "version it replaces (the cached full corpus) at the same corpus size. Caching the full corpus loses nothing (it has the fewest serious errors at both sizes). Retrieval loses nothing "
              + ("on the 7-document deal room" if not any(v for (r, sc), v in retr_loss.items() if sc == 1) else "even on the 7-document deal room")
              + (f"; at 21 documents BM25+rerank does ({fr4(h3['answers_with_material_error'])} vs {fr4(c3['answers_with_material_error'])})"
                 if retr_loss[("hybrid_rag_rerank_citations", 3)] else "")
              + (", and the paired rung's " + fr4(p3["answers_with_material_error"])
                 + (" is also clearly higher" if retr_loss[("cached_rerank_hybrid", 3)] else " is higher but its interval still overlaps")
                 if retr_loss[("hybrid_rag_rerank_citations", 3)] else "")
              + ". Against the naive full corpus the retrieval rungs' intervals overlap. Blind grader, one pass per answer; the deterministic key facts move less than the grader's error count.")
    else:
        claim("Cat 4", "Pair hybrid retrieval (reranking + chunk filtering) with context caching", "no rerun data for the paired rung", "NOT TESTABLE",
              q4_source.get("reason") or "the Category 4 rerun summary has no paired-rung cells")
        claim("Cat 4", "…without losing answer quality (implicit)", "no quality data", "NOT TESTABLE", q4_source.get("reason") or "")

    # ---------------- Cat 5
    u5 = cat5_units(seeds)
    order5 = ["unbounded_sonnet_loop", "bounded_sonnet_cached_gate", "hybrid_haiku_sonnet_governed"]
    s5 = summarize_rungs(u5, order5)
    q5 = {r: {"exact_match": sum(1 for u in u5[r] if (u["evaluation"] or {}).get("exact_match")),
              "tool_precision_median": med([(u["evaluation"] or {}).get("tool_precision_pct") for u in u5[r]]),
              "evidence_recall_min": min((u["evaluation"] or {}).get("evidence_recall_pct", 0) for u in u5[r]),
              "gate_verified": sum(1 for u in u5[r] if (u["evaluation"] or {}).get("gate_verified")),
              "steps": [u["steps"] for u in u5[r]], "escalations": sum(1 for u in u5[r] if u["escalated"])} for r in order5}
    res["categories"]["cat5"] = {"rungs": s5, "quality": q5}
    ub5 = s5["unbounded_sonnet_loop"]
    claim("Cat 5", "Input 25k–150k+ tokens per task", f"unbounded {ub5['prompt_tokens_range'][0]/1e3:.0f}k–{ub5['prompt_tokens_range'][1]/1e3:.0f}k; bounded {s5['bounded_sonnet_cached_gate']['prompt_tokens_range'][0]/1e3:.0f}k–{s5['bounded_sonnet_cached_gate']['prompt_tokens_range'][1]/1e3:.0f}k (mostly cache reads)", verdict(True))
    claim("Cat 5", "Output 1,500–8,000 tokens per task", f"unbounded {ub5['output_tokens_range'][0]:,}–{ub5['output_tokens_range'][1]:,}; bounded {s5['bounded_sonnet_cached_gate']['output_tokens_range'][0]:,}–{s5['bounded_sonnet_cached_gate']['output_tokens_range'][1]:,}",
          verdict(False, True), "Low end or just under: these are short 3–7-step loops.")
    sv5b = pct_saving(ub5["cost_per_1k_billed"], s5["bounded_sonnet_cached_gate"]["cost_per_1k_billed"])
    sv5h = pct_saving(ub5["cost_per_1k_billed"], s5["hybrid_haiku_sonnet_governed"]["cost_per_1k_billed"])
    claim("Cat 5", "Max-step budgets + deterministic guardrails + small-model routing for routine tool calls",
          f"bounded −{sv5b:.0f}%, + Haiku routing −{sv5h:.0f}%; voucher exact-match 3/3 on every rung; tool precision {q5['unbounded_sonnet_loop']['tool_precision_median']:.0f}% → 100%",
          verdict(True), f"Holds on n=3 invoices; Haiku escalated to Sonnet on {q5['hybrid_haiku_sonnet_governed']['escalations']}/3. Each rung changes step cap, SOP caching and SQL projection at once, so the saving can't be split between them.")

    # ---------------- Cat 6 (fair rerun: 4 arms x 3 incidents x 5 repeats)
    u6, cat6_verdict_source = cat6_units()
    order6 = CAT6_ARMS
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
                  "mean_total_tokens": st.mean(tok(u["calls"])["total"] for u in u6[r])}
    prefix6 = med([u["turn1_prefix"] for u in u6["isolated_cached_gate"]])
    res["categories"]["cat6"] = {"rungs": s6, "cpo": cpo, "source": "fair rerun", "verdict_source": cat6_verdict_source,
                                 "records": sum(len(u6[r]) for r in order6), "repo_prefix_tokens": prefix6}
    sbo, sbm, iso6, tie6 = (s6[a] for a in order6)
    n6 = cpo["shared_bus_original"]["runs"]
    verdict_note = "" if cat6_verdict_source == "rescored" else " Verdicts are as recorded: the re-scored section of analysis/cat6_fair_rerun.json was missing."
    rk = lambda v, key: f"{v[key][0]/1e3:.0f}k–{v[key][1]/1e3:.0f}k"  # noqa: E731
    claim("Cat 6", "Input 100k–1M+ tokens per run",
          f"n={n6} runs per arm: shared bus {rk(sbo, 'prompt_tokens_range')} (matched instructions {rk(sbm, 'prompt_tokens_range')}); isolated + cached {rk(iso6, 'prompt_tokens_range')}; tiered {rk(tie6, 'prompt_tokens_range')}",
          verdict(False, True), f"Only the shared-bus arms reach the band, all of it uncached. The isolated swarms send ~{iso6['prompt_tokens_median']/1e3:.0f}k per run, mostly cache reads of a ~{prefix6/1e3:.1f}k-token repo prefix.")
    rk1 = lambda v: f"{v['output_tokens_range'][0]/1e3:.1f}k–{v['output_tokens_range'][1]/1e3:.1f}k"  # noqa: E731
    mt6 = sum(cpo[a]["turns_at_max_tokens"] for a in order6)
    tlen = sorted({len(u["calls"]) for a in order6 for u in u6[a]})
    turns6 = f"{tlen[0]}" if len(tlen) == 1 else f"{tlen[0]}–{tlen[-1]}"
    claim("Cat 6", "Output 10k–50k+ tokens per run",
          f"shared bus, original instructions {rk1(sbo)}; matched instructions {rk1(sbm)}; isolated + cached {rk1(iso6)}; tiered {rk1(tie6)}",
          verdict(False, True), f"Only the shared bus with its original \"exhaustive\" instructions writes 10k+. With the governed word limits every arm writes ~4–7k, below the band, so output length follows the instructions, not the context design. {mt6} of {sum(cpo[a]['turns_total'] for a in order6)} turns stopped on max_tokens. All runs are {turns6} turns on a single-file fix.")
    sb_tot, ti_tot = cpo["shared_bus_original"]["mean_total_tokens"], cpo["tiered_gate"]["mean_total_tokens"]
    claim("Cat 6", "1.5M–10M+ tokens per developer per day", f"not measurable: {res['categories']['cat6']['records']} single runs, no per-developer daily traffic", "NOT TESTABLE",
          f"Would take ~{1.5e6/sb_tot:.0f}–{10e6/sb_tot:.0f} shared-bus runs/dev/day (mean {sb_tot/1e3:.0f}k tokens/run), or ~{1.5e6/ti_tot:.0f}–{10e6/ti_tot:.0f} tiered runs (mean {ti_tot/1e3:.0f}k).")
    c_sb, c_ti = cpo["shared_bus_original"]["cpo"], cpo["tiered_gate"]["cpo"]
    same_rate = len({cpo[a]["verified"] / cpo[a]["runs"] for a in order6}) == 1
    claim("Cat 6", "Isolate sub-agent contexts, cache the shared repo prefix, measure cost per verified outcome (CpO)",
          "CpO per verified fix: " + "; ".join(f"{RUNG_LABELS[a].split(' (')[0]} {_money(cpo[a]['cpo'])} ({cpo[a]['verified']}/{cpo[a]['runs']} verified)" for a in order6),
          verdict(False, True),
          f"Cost per verified fix falls ~{c_sb / c_ti:.0f}× from the shared bus to the tiered swarm "
          f"(isolation + caching alone, same instructions: {_money(cpo['shared_bus_matched_gate']['cpo'])} → {_money(cpo['isolated_cached_gate']['cpo'])}), "
          + ("while the verified rate is the same in every arm. " if same_rate else "and the verified rate differs between arms. ")
          + "The tasks are too easy to show a quality effect (ceiling): every saving is cost per run, and CpO adds nothing over it here, so the outcome side of the claim is untested."
          + verdict_note)

    # ---------------- cross-category scale
    scale = {
        "Cat 1 (item)": s1["haiku_calibrated"]["total_tokens_median"],
        "Cat 2 (document)": s2["sonnet_unbounded"]["total_tokens_median"],
        "Cat 3 (10-turn session)": s3["naive_full_history"]["total_tokens_median"],
        "Cat 4 (4-question audit)": s4[_cat4_key("naive_full_corpus", 1)]["total_tokens_median"],
        "Cat 4 (single question)": med([tok(q["calls"])["total"] for u in u4[_cat4_key("naive_full_corpus", 1)] for q in u["per_question"]]),
        **({"Cat 4 (single question, 3× corpus)": med([tok(q["calls"])["total"] for u in u4[_cat4_key("naive_full_corpus", 3)] for q in u["per_question"]])}
           if u4.get(_cat4_key("naive_full_corpus", 3)) else {}),
        "Cat 5 (invoice)": s5["unbounded_sonnet_loop"]["total_tokens_median"],
        "Cat 6 (incident run, shared bus)": s6["shared_bus_original"]["total_tokens_median"],
    }
    res["scale"] = scale
    claim("Matrix", "Monotonic token scale: Cat 1 < Cat 2 < Cat 3 < Cat 4 < Cat 5 << Cat 6",
          "; ".join(f"{k} {v/1e3:.1f}k" for k, v in scale.items()), verdict(False, True),
          "1 < 2 < {3,4,5} < 6 holds. The order of 3, 4 and 5 depends on the unit: a 10-turn session bills more than a single RAG question or a whole invoice.")

    # ---------------- pricing sensitivity
    for cat, rungs in (("cat3", s3), ("cat4", s4), ("cat5", s5), ("cat6", s6)):
        for r, v in rungs.items():
            if abs(v["cost_per_1k_billed_repo_card"] - v["cost_per_1k_billed"]) > 0.005 * max(1, v["cost_per_1k_billed"]):
                res["pricing_notes"].append({"category": cat, "rung": r, "repo_card": v["cost_per_1k_billed_repo_card"], "official": v["cost_per_1k_billed"]})
    long_haiku = [(cat, r) for cat, us in (("cat1", u1), ("cat3", u3), ("cat4", u4), ("cat5", u5), ("cat6", u6))
                  for r, lst in us.items() for u in lst for c in u["calls"] if c["model"] == HAIKU and prompt_tokens(c) > HAIKU_LONG_PROMPT_THRESHOLD]
    res["haiku_calls_over_100k_prompt"] = len(long_haiku)
    return res


# ------------------------------------------------------------------ 4. writers
RUNG_LABELS = {
    "sonnet_naive": "Sonnet 5.5 · free-text prose", "haiku_naive": "Haiku 5.5 · free-text prose",
    "haiku_calibrated": "Haiku 5.5 · strict JSON schema", "gemini_decision": "Gemini Decision 1 · decisions API",
    "haiku_calibrated_batch": "Haiku 5.5 · strict JSON · Batch API (−50%)",
    "sonnet_unbounded": "Sonnet · unbounded long-form", "sonnet_templated": "Sonnet · section template + caps",
    "haiku_templated": "Haiku · section template + caps",
    "naive_full_history": "Full history, no cache", "prefix_cached_history": "Full history + cached handbook prefix",
    "prefix_cached_summarized": "Cached prefix + sliding-window summary",
    "naive_full_corpus": "Full corpus, no cache, no citations", "cached_full_corpus_citations": "Full corpus, cached + native citations",
    "hybrid_rag_rerank_citations": "BM25 28→10 + Haiku rerank 10→5 + citations",
    "unbounded_sonnet_loop": "Unbounded Sonnet ReAct loop", "bounded_sonnet_cached_gate": "4-step budget + cached SOP + policy gate",
    "hybrid_haiku_sonnet_governed": "Haiku-first, Sonnet on escalation",
    "shared_bus_original": "Shared bus, original instructions (Sonnet)",
    "shared_bus_matched_gate": "Shared bus, matched instructions + gate (Sonnet)",
    "isolated_cached_gate": "Isolated + cached repo prefix + gate (Sonnet)",
    "tiered_gate": "Tiered: Haiku agents + Sonnet patch author (isolated + cached + gate)",
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


def _cat2_owner_issue(res):
    q = res["categories"]["cat2"].get("quality")
    ai = [(RUNG_LABELS.get(r, r), q[r]["action_items"]) for r in ("sonnet_templated", "haiku_templated") if q and q.get(r) and q[r].get("action_items")]
    if not ai:
        return ("12. **The Category 2 template requires an owner and a time window for every action item** (`action_plan` items: `owner` and `target_window` are required, "
                "exactly 3 items), even when the source gives none; the per-item judge results needed to count the effect were not available.")
    per = "; ".join(f"{name} {a['flagged']}/{a['total']} ({a['flagged_serious']} serious)" for name, a in ai)
    return ("12. **The Category 2 template requires an owner and a time window for every action item** (`action_plan` items: `owner` and `target_window` are required, "
            f"exactly 3 items), even when the source gives none. Measured: the judge flagged an owner or deadline the source does not support in this many templated action items: {per}. *Not changed:* the model-facing prompt and schema are as captured."
            + _cat2_fix_sentence(res["categories"]["cat2"].get("template_fix"))
            + (" The app keeps the original template; the follow-up is shown beside it." if res["categories"]["cat2"].get("template_fix") else ""))


CAT4_LABELS = {
    "naive_full_corpus": "Full corpus, no cache, no citations",
    "cached_full_corpus_citations": "Full corpus, cached + native citations",
    "hybrid_rag_rerank_citations": "BM25 + Haiku rerank → 5 chunks + citations",
    "cached_rerank_hybrid": "Haiku reranks the cached full corpus → 5 chunks + citations (paired; rerun only)",
}
CAT4_SCALE_LABEL = {1: "7 docs", 3: "21 docs"}


def _cat4_absence_issue_text():
    """Counts of the grader's serious errors on the retrieval rungs that claim something is absent (from the analysis file)."""
    try:
        d = json.loads(CAT4_QUALITY_ANALYSIS.read_text())
        me = [m for m in d["for_lead_review"]["material_errors"]
              if m["source"] == "rerun" and m["rung_id"] in ("hybrid_rag_rerank_citations", "cached_rerank_hybrid")]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return ""
    if not me:
        return ""
    absent = [m for m in me if re.search(r"\bno\b|\bnot (in|state|specify|quantif|give|contain)|missing|does not|do not|absent|cannot be quantified",
                                         m["claim_quote"].lower())]
    gate = [m for m in absent if "noc" in (m["claim_quote"] + m["problem"]).lower() or "escrow" in (m["claim_quote"] + m["problem"]).lower()]
    return (f"Of the {len(me)} serious errors the grader reported on the two retrieval rungs, {len(absent)} claim the documents lack something they contain, "
            f"and {len(gate)} of those concern the NOC/escrow gate (keyword count over `analysis/cat4_quality_rerun.json`). ")


def _nstar(r):
    return "—" if r.get("n_star") is None else f"{r['n_star']:.1f}"


def _cat4_label(key):
    rung, scale = key.split("|")
    return f"{CAT4_LABELS[rung]} · {CAT4_SCALE_LABEL.get(int(scale), scale)}"


def _render_cat4(c):
    L = []
    rungs, pq = c["rungs"], c["per_question"]
    stats = c.get("call_stats")
    first = next(iter(rungs.values()))
    if c["source"] == "quality rerun":
        L += [f"### 4. {TITLE['cat4']} (per 1k questions; n={first['n'] * 4} answers per row)", "",
              f"Source: the quality rerun, {stats['records']} records = {stats['answers']} answers (4 rungs × 2 corpus sizes × 3 sessions of 8 questions; "
              "each session asked audit-01 then audit-02, so one unit here is a 4-question audit and each session gives two). Corpus sizes: the app's 7-document deal "
              "room, and 21 documents (two synthetic look-alike suppliers added). Every question carried a one-line supplier-scope prefix. The golden replays are repeat 0 "
              "of the three app rungs at 7 documents. Synthesis stop reasons: "
              + ", ".join(f"{k} {v}" for k, v in stats["synthesis_stop_reasons"].items())
              + f"; {stats['synthesis_calls_with_thinking']}/{stats['answers']} answers used extended thinking.", ""]
    else:
        L += [f"### 4. {TITLE['cat4']} (per 1k questions)", "", "Source: the Category 4 golden replays (the quality-rerun records could not be read).", ""]
    L += ["| Rung · corpus | Billed | Warm | Cold | Pre-fix card (billed) | Synthesis prompt (median) | Answer output (median) | Citations / answer (median) | Answers with 0 citations | Stop reasons |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for key, v in pq.items():
        cit = "—" if key.startswith("naive") else f"{v['citations_median']:.0f}"
        zero = "—" if key.startswith("naive") else f"{v['questions_with_zero_citations']}/{v['answers']}"
        L.append(f"| {_cat4_label(key)} | {_money(v['cost_per_1k_q_billed'])} | {_money(v['cost_per_1k_q_warm'])} | {_money(v['cost_per_1k_q_cold'])} | "
                 f"{_money(v['cost_per_1k_q_billed_repo_card'])} | {_k(v['synth_prompt_median'])} | {v['synth_output_median']:.0f} | {cit} | {zero} | "
                 + ", ".join(f"{k} {n}" for k, n in sorted(v["stop_reasons"].items())) + " |")
    L += ["", "*Cold* here: the first question of each 4-question audit writes the cache (the rerun billed one write per 8-question session). "
          "Cost includes the Haiku reranker where the rung has one; the prompt column is the answering (synthesis) call.", ""]
    q, be, src = c.get("quality"), c.get("break_even"), c.get("quality_source") or {}
    if q:
        L += [f"Answer quality (read from `{src['file']}`, keys version `{src.get('keys_version')}`; {src.get('answers')} answers, {src.get('judged')} graded by a blind "
              f"grader (`{src.get('judge_model')}`, not a model under test, {src.get('judge_passes')} pass per answer); deterministic answer-key measures; 95% Wilson intervals):", "",
              "| Rung · corpus | Key facts stated | Citations at expected clauses | Expected clauses cited | Expected clauses kept by retrieval | Other suppliers' clauses selected | "
              "Grader correctness (1–5) | Grader completeness (1–5) | Answers with a serious error | Contaminated answers |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]

        def qm(m):
            if not m or not m.get("total"):
                return "—"
            ci = f" ({m['ci_low']*100:.0f}–{m['ci_high']*100:.0f}%)" if m.get("ci_low") is not None else ""
            return f"{m['hits']}/{m['total']} = {m['hits']/m['total']*100:.0f}%{ci}"
        for key in pq:
            v = q.get(key)
            if not v:
                continue
            L.append(f"| {_cat4_label(key)} | {qm(v['fact_recall'])} | {qm(v['citations_at_expected'])} | {qm(v['expected_chunk_recall'])} | {qm(v['recall_after_rerank'])} | "
                     f"{qm(v['distractors_selected'])} | {v['correctness_mean']:.2f} | {v['completeness_mean']:.2f} | {qm(v['answers_with_material_error'])} | {qm(v['contaminated_answers'])} |")
        L += ["", "*Key facts*: fixed answer key (4–7 facts per question), deterministic matching. *Expected clauses kept by retrieval*: after reranking (rows without retrieval: —). "
              "*Serious error*: a statement the grader marked material (wrong amount, party, date, condition or precedence, or a claim that the documents lack something they contain). "
              "*Contaminated*: states another supplier's value for a keyed fact or cites another supplier's clause (the one case named the other supplier while excluding its figure).", ""]
    else:
        L += [f"Answer quality: not available ({src.get('reason')}).", ""]
    if be:
        for scale in ("1", "3"):
            rows = be.get(scale) or []
            if not rows:
                continue
            L += [f"Break-even, {CAT4_SCALE_LABEL[int(scale)]} (questions that must share one cache write before A is cheaper than B; cost(N) = one-off cache-write premium + N × warm $/question):", "",
                  "| A vs B | A premium | A warm $/question | B premium | B warm $/question | N* | Result |", "|---|---:|---:|---:|---:|---:|---|"]
            for r in rows:
                L.append(f"| {CAT4_LABELS[r['a']]} vs {CAT4_LABELS[r['b']]} | ${r['premium_a_usd']:.4f} | ${r['per_question_a_usd']:.4f} | ${r['premium_b_usd']:.4f} | "
                         f"${r['per_question_b_usd']:.4f} | {_nstar(r)} | {r['verdict']} |")
            L.append("")
    return L


def render_markdown(res):
    L = []
    dd = res["dedup"]["totals"]
    verdicts = Counter(c["verdict"] for c in res["claims"])
    L += [
        "# Six AI Archetypes deck: claims checked against the NovaMart traces",
        "",
        "_Generated by `backend/scripts/validate_deck_claims.py` from `backend/replays/*_golden_replays.json` (Categories 1, 2, 5), the Category 2 blind-judge quality summary "
        "(`backend/replays/cat2_quality_summary.json`), the Category 3 quality rerun "
        "(`backend/experiments/cat3_quality/runs.jsonl` + `backend/replays/cat3_quality_summary.json`), the Category 4 quality rerun "
        "(`backend/experiments/cat4_quality/runs.jsonl` + `backend/replays/cat4_quality_summary.json`), the Category 6 fair rerun "
        "(`backend/experiments/cat6_fair_rerun/runs.jsonl` + `analysis/cat6_fair_rerun.json`) and `backend/traces/`. Re-run the script after re-capturing replays._",
        "",
        "## How the data was de-duplicated",
        "",
        f"`backend/traces/` holds **{dd['raw_traces']} trace files** but only **{dd['canonical_runs']} distinct canonical runs**. "
        f"{dd['raw_by_mode'].get('replay', 0)} files are replay-mode copies written each time the UI served a golden replay; one run appears up to {dd['max_duplicates_of_one_run']}×. "
        "Averaging the trace index weights each run by how often it was viewed, and it mixes in older captures with different `max_tokens` settings.",
        "",
        "| Category | Trace files | Distinct fingerprints | Canonical runs | Superseded captures | Rollups | Live / error |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cat, b in res["dedup"]["by_category"].items():
        cl = b["classes"]
        L.append(f"| {cat} | {b['raw_traces']} | {b['distinct_fingerprints']} | {b['canonical_runs']} | {cl.get('superseded capture (older golden-replay version)', 0)} | "
                 f"{cl.get('rollup of canonical runs (session/audit sum)', 0)} | {cl.get('ad-hoc live run', 0)} / {cl.get('error (live, no tokens)', 0)} |")
    L += [
        "",
        "Only the newest seed trace per (category, model, pattern, item) counts as canonical; older seeds for the same slot, such as the first Category 3 and "
        "Category 6 captures, and replays of them are counted as superseded captures.",
        "",
        "**Unit of analysis:** one canonical run per (item × rung), taken from the current golden-replay files, which match the seed traces one-to-one. "
        "Categories 3, 4 and 6 are the exceptions. Category 3 uses all 18 quality-rerun records (3 rungs × 2 sessions × 3 repeats, n=6 per rung); its golden replays are repeat 0 of every rung. "
        "Category 4 uses all 24 quality-rerun sessions (4 rungs × 2 corpus sizes × 3 sessions of 8 questions, 192 answers, n=24 per row); its golden replays are repeat 0 of the three app rungs at the 7-document corpus. "
        "Category 6 uses all 60 fair-rerun records (4 arms × 3 incidents × 5 repeats, n=15 per arm); its golden replays are repeat 0 of three of those arms. "
        "Costs are recomputed per API call from recorded token counts, priced by the model that served the call. "
        "The traces' own `finops` blocks are not used, so the results don't depend on how the app priced them.",
        "",
        "**Cost views.** *Billed*: cache tokens exactly as the API reported them during capture. "
        "*Warm*: every cached-prefix token is a cache read (steady state). "
        "*Cold*: the first call per model in each unit writes the prefix. "
        "All dollar figures use Anthropic's published rates, which `pricing.py` now matches. The *pre-fix card* column shows the repo's earlier $0.20 Sonnet cache-read rate.",
        "",
        "## Scorecard",
        "",
        " · ".join(f"{BADGE[k]}: **{verdicts.get(k, 0)}**" for k in BADGE),
        "",
        "Verdict rule: **Supported** means the measurement falls inside the claimed range or clears the threshold. "
        "**Partly** means the direction holds but the magnitude is outside the range, or a confound limits the conclusion. "
        "**Not supported** means the data contradicts the claim.",
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
        rungs = res["categories"][cat]["rungs"]
        first = next(iter(rungs.values()))
        L += [f"### {cat[-1]}. {TITLE[cat]} (per 1k {UNIT[cat]}s, n={first['n']} per rung)", "",
              "| Rung | Billed | vs first rung | Warm | Cold | Pre-fix card (billed) | Prompt tok (median) | Output tok (median) | Output share of cost |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        base = first["cost_per_1k_billed"]
        for r, v in rungs.items():
            if "n" not in v:
                L.append(f"| {RUNG_LABELS.get(r, r)} | {_money(v['cost_per_1k_billed'])} | −{pct_saving(base, v['cost_per_1k_billed']):.1f}% | | | | | | |")
                continue
            sv = pct_saving(base, v["cost_per_1k_billed"])
            L.append(f"| {RUNG_LABELS.get(r, r)} | {_money(v['cost_per_1k_billed'])} | {'—' if r == next(iter(rungs)) else f'−{sv:.1f}%'} | "
                     f"{_money(v['cost_per_1k_warm'])} | {_money(v['cost_per_1k_cold'])} | {_money(v['cost_per_1k_billed_repo_card'])} | "
                     f"{_k(v['prompt_tokens_median'])} | {_k(v['output_tokens_median'])} | {v['output_cost_share_median']*100:.0f}% |")
        L.append("")
        c = res["categories"][cat]
        if cat == "cat1":
            a = c["accuracy"]
            L.append("Accuracy (42 field checks over 12 items): " + ", ".join(f"{RUNG_LABELS[r]} {v['fields_matched']}/{v['fields_total']}" for r, v in a.items())
                     + f". Naive runs that hit `max_tokens=2048`: Sonnet {c['naive_runs_hitting_max_tokens_2048']['sonnet_naive']}/12, Haiku {c['naive_runs_hitting_max_tokens_2048']['haiku_naive']}/12.")
        if cat == "cat2":
            rg = c["section_regen"]
            L.append(f"Single-section regeneration (n={rg[SONNET]['n']} per model): Sonnet {_money(rg[SONNET]['cost_per_1k'])}/1k, Haiku {_money(rg[HAIKU]['cost_per_1k'])}/1k. "
                     f"The deck's hybrid workflow, a Haiku draft plus one Sonnet section fix, costs {_money(c['haiku_draft_plus_1_sonnet_section_regen_per_1k'])}/1k documents, "
                     f"−{pct_saving(rungs['sonnet_unbounded']['cost_per_1k_billed'], c['haiku_draft_plus_1_sonnet_section_regen_per_1k']):.0f}% vs unbounded Sonnet.")
            q, qsrc = c.get("quality"), c.get("quality_source") or {}
            L.append("")
            if q:
                pc = qsrc["position_consistency"]
                L += [f"Draft quality (read from `{qsrc['file']}`, keys version `{qsrc.get('keys_version')}`): graded by a blind LLM judge (`{qsrc['judge_model']}`, "
                      f"not one of the models under test), {qsrc['passes']} rubric passes per draft, {qsrc['drafts_per_cell']} draft per rung × {qsrc['documents']} documents; "
                      f"head-to-head pairs shown in both orders (position-consistent in {pc[0]}/{pc[1]} pairs). Fact coverage is deterministic (fixed answer key). "
                      "The lead verified the serious errors' claims against the source payloads.", "",
                      "| Rung | Core facts | Detail facts | Accuracy | Coverage | Clarity | Actionability | Concision | Serious / minor errors | "
                      "Numbers not in source (derived correct / derived wrong / unverifiable / not a claim / no majority) | Head-to-head W–L–T | Action items with an owner or deadline flagged |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|"]
                for r in rungs:
                    v = q.get(r)
                    if not v:
                        continue
                    vd = v["verdicts"]
                    h2h = v["h2h"]
                    tot = [sum(x[k] for x in h2h.values()) for k in ("wins", "losses", "ties")]
                    per = "; ".join(f"vs {RUNG_LABELS.get(o, o)} {x['wins']}–{x['losses']}–{x['ties']}" for o, x in h2h.items())
                    a = v.get("action_items")
                    L.append(f"| {RUNG_LABELS.get(r, r)} | {v['core']['hits']}/{v['core']['total']} | {v['detail']['hits']}/{v['detail']['total']} | "
                             + " | ".join(f"{v['rubric'][k]:.2f}" for k in CAT2_DIMS)
                             + f" | {v['serious']} / {v['minor']} | {v['not_in_source']}: " + " / ".join(str(vd[k]) for k in CAT2_VERDICTS)
                             + f" | {tot[0]}–{tot[1]}–{tot[2]} ({per}) | {('—' if not a else str(a['flagged']) + '/' + str(a['total']) + ' (' + str(a['flagged_serious']) + ' serious)')} |")
                L += ["", "*Grades* are rubric means on a 1–5 scale over all passes and documents. *Serious errors* are distinct factual errors the judge marked material "
                      "(de-duplicated across passes). *Numbers not in source*: numeric tokens in the draft that the deterministic check could not find in the source, "
                      "with the judge's majority verdict. *Action items flagged*: templated action items whose owner or time window the judge reported as an error."]
            else:
                L.append(f"Draft quality: not available ({qsrc.get('reason')}).")
            fx, fsrc = c.get("template_fix"), c.get("template_fix_source") or {}
            L.append("")
            if fx:
                L += [f"**Follow-up: the template plus one \"Not stated in source\" sentence** (read from `{fsrc['file']}`; {fsrc['drafts']} fresh drafts, "
                      f"{fsrc['per_cell']} per document × model × template; blind judge `{fsrc['judge_model']}`, {fsrc['passes']} pass per draft, {fsrc['judge_calls']} calls). "
                      "Not the app's template, which is the original. Added sentence: \"" + fx["added_instruction"] + "\"", "",
                      "| Model | Template | Serious errors / draft | Accuracy | Coverage | Actionability | Owners not in source | Time windows not in source | Detail facts | $ / 1k docs |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
                for m in ("sonnet", "haiku"):
                    for arm in CAT2_FIX_ARMS:
                        v = fx["cells"].get(f"{arm}|{m}")
                        if not v:
                            continue
                        r_ = v["rubric"]
                        L.append(f"| {'Sonnet 5.5' if m == 'sonnet' else 'Haiku 5.5'} | {'original (app)' if arm == 'template_original' else '+ not-stated sentence'} | "
                                 f"{v['serious']:.2f} | {r_['factual_accuracy']:.2f} | {r_['coverage']:.2f} | {r_['actionability']:.2f} | "
                                 f"{v['owner']['unsupported']}/{v['items']} ({v['owner']['not_stated']} not stated) | {v['window']['unsupported']}/{v['items']} ({v['window']['not_stated']} not stated) | "
                                 f"{v['detail']['hits']}/{v['detail']['total']} | {_money(v['cost_per_1k'])} |")
                h = fx["h2h"]
                fmt = lambda b: f"{b['overall']['wins']}–{b['overall']['losses']}–{b['overall']['ties']} (accuracy {b['accuracy']['wins']}–{b['accuracy']['losses']}–{b['accuracy']['ties']}, usefulness {b['usefulness_to_reader']['wins']}–{b['usefulness_to_reader']['losses']}–{b['usefulness_to_reader']['ties']})"  # noqa: E731
                L += ["", f"Head-to-head (W–L–T for the template with the sentence): vs the original template on the same document, model and repeat {fmt(h['vs_original'])}; "
                      f"vs the stored unbounded draft {fmt(h['vs_unbounded'])}. *Not in source* uses the follow-up's deterministic rule (name or date not found in the source)."]
            else:
                L.append(f"Follow-up: not available ({fsrc.get('reason')}).")
        if cat == "cat3":
            if c["source"] == "quality rerun":
                L += [f"Source: the quality rerun, {c['records']} records (3 rungs × 2 sessions × 3 repeats). Costs cover turns 1–10 and the compactions before them; "
                      "the recall-probe phase is excluded. The golden replays are repeat 0 of every rung.", ""]
            else:
                L += ["Source: the Category 3 golden replays (the quality-rerun records could not be read).", ""]
            L += ["Context per turn (prompt tokens, mean per session):", "",
                  "| Rung | Turn 1 | Turn 3 | Turn 6 | Turn 10 | Slope (tok/turn) | Peak context | Compactor calls / session |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
            for r, gr in c["context_growth"].items():
                L.append(f"| {RUNG_LABELS[r]} | {_k(gr['turn1'])} | {_k(gr['turn3'])} | {_k(gr['turn6'])} | {_k(gr['turn10'])} | +{gr['slope_tokens_per_turn']:,.0f} | {_k(gr['peak_context'])} | {gr['compactor_calls_per_session']:.0f} |")
            L.append("| *Deck illustration* | *1.2k* | *6.5k* | *14k* | *25k+* | *~+2.6k* | | |")
            L.append("")
            q, qsrc = c["quality"], c["quality_source"]
            if q:
                L += [f"Answer quality (fixed answer key, keys version `{qsrc.get('keys_version')}`, read from `{qsrc['file']}`; 95% Wilson intervals):", "",
                      "| Rung | Sessions | Answers grounded (turns 1–9) | Final-summary details | …from turns 1–3 | …from turns 4–6 | …from turns 7–9 | Recall questions answered |",
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
        if cat == "cat5":
            L.append("Quality: " + "; ".join(f"{RUNG_LABELS[r]}: exact voucher {q['exact_match']}/3, tool precision {q['tool_precision_median']:.0f}%, policy gate verified {q['gate_verified']}/3, steps {q['steps']}"
                                            for r, q in c["quality"].items()) + ".")
        if cat == "cat6":
            src = "re-scored with the current sandbox" if c["verdict_source"] == "rescored" else "as recorded (re-scored section missing)"
            L.append(f"Source: the fair rerun, {c['records']} records; sandbox verdicts {src}.")
            L.append("")
            L.append("| Arm | Verified (final) | First attempt verified | Checks passed | Cost / run (billed) | CpO billed | CpO warm | CpO cold | Turns stopped on max_tokens | Retries triggered |")
            L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for r, v in c["cpo"].items():
                L.append(f"| {RUNG_LABELS[r]} | {v['verified']}/{v['runs']} | {v['first_attempt_verified']}/{v['runs']} | {v['checks_passed']}/{v['checks_total']} | "
                         f"{_money(v['cost_per_run'])} | {_money(v['cpo'])} | {_money(v['cpo_warm'])} | {_money(v['cpo_cold'])} | "
                         f"{v['turns_at_max_tokens']}/{v['turns_total']} | {v['retries_triggered']} |")
        L.append("")

    L += ["## Token scale across archetypes (median total tokens per unit, deck-typical rung)", "", "| Unit | Tokens |", "|---|---:|"]
    L += [f"| {k} | {_k(v)} |" for k, v in res["scale"].items()]
    L += ["", "## Pricing check", "",
          "| Rate ($/MTok) | Repo `pricing.py` (before fix → now) | Anthropic published | Effect |", "|---|---:|---:|---|",
          "| Sonnet 5.5 input / output | 2.00 / 10.00 | 2.00 / 10.00 | — |",
          "| Sonnet 5.5 cache read | **0.20 → 0.10** | **0.10** | **Fixed.** The old rate overstated every cached Sonnet rung by ~2–10%; stored traces have been re-priced |",
          "| Sonnet 5.5 cache write (5-min) | 2.50 | 2.50 (1.25× input, assumed) | — |",
          "| Haiku 5.5 input / output | 0.10 / 0.50 | 0.10 / 0.50 (≤100K prompt) | Prompts above 100K tokens cost 0.50 / 2.50; not modelled, but no captured Haiku call exceeds 100K "
          f"({res['haiku_calls_over_100k_prompt']} found) |",
          "| Gemini Decision 1 | 0.10 / 0 | not verified | Non-Anthropic; kept as-is |",
          "",
          "## Issues found in the lab code and data",
          "",
          "1. **Trace `finops` is not billed cost.** Category 5 and 6 rollups store a *modelled* cold-cache cost (`_compute_step_cold_warm`) instead of the cache tokens the API returned. "
          "This is by design and remains. *Fixed:* the rollups priced all output at Sonnet's $10/MTok (and the seed script priced mixed runs at one model's rates), "
          "so some traces had `total_cost_usd` < `output_cost_usd`. All four now use `rollup_multi_call_finops`, which prices each call at its own model's rate.",
          "2. **CpO was zero for failed runs.** *Fixed:* `cpo_*_per_1k_usd` is now `None` for an unverified run, and the portfolio CpO and savings are `None` when a rung has no verified outcomes (`cat6_swarms/runner.py`).",
          "3. **Naive rungs are truncated (Category 1).** Category 1 prose hits `max_tokens=2048` on most items, so its naive costs are lower bounds.",
          "4. **Cross-rung cache warming.** Capture order lets later rungs and items read caches warmed by earlier ones (e.g. Category 4 audit-02 read the cache audit-01 wrote in the same session, so it shows zero cache writes). "
          "The *billed* column includes this effect; the *cold* column removes it. The Category 6 fair rerun avoids it: each run writes its own cache (a per-run nonce in the cached prefix).",
          "5. **Trace index is not de-duplicated.** `index.jsonl`/`summarize_traces()` average replays, superseded captures and session rollups together. "
          "Any dashboard built on it over-weights frequently viewed items.",
          "6. **6 error traces** (Gemini Decision × free-text prose, live, `Connection error`) hold zero tokens and should be excluded from averages.",
          "7. **The first Category 6 capture was biased and has been replaced.** Its shared-bus agents were truncated at `max_tokens=3200`, the capture script rejected and re-ran "
          "governed runs that failed the sandbox, and the governed patch author had explicit hints and word limits the shared-bus author lacked. "
          "The fair rerun (4 arms × 3 incidents × 5 repeats, equal output caps, per-run cold caches, no outcome-based selection, a shared-bus arm with matched instructions) replaces it; "
          "the capture script now rejects runs only for infrastructure failures.",
          "8. **AST-SEC-01 false positive (fixed).** The constant-time-comparison check treated a comparison against a module-level scheme-prefix constant "
          "(`_SIG_PREFIX = \"sha256=\"`) as a direct signature `==`. Three shared-bus inc-02 runs were scored 9/10 for it. Module-level names bound once to a literal now count as constants; "
          "the Category 6 numbers here use the re-scored verdicts, and the first capture's golden verdicts were unchanged by the fix.",
          _cat3_thinking_issue(res),
          "10. **The first Category 3 capture hard-coded the compaction stop reason** (`\"end_turn\"` for every summariser call), so a truncated compaction could not be seen. "
          "*Fixed:* the live path records the API's real `stop_reason` for compactions, and the golden replays, rebuilt from the quality rerun, carry the recorded stop reason of every call.",
          "11. **The Category 2 capture script wrote a constant stop reason** (`\"end_turn\"` for every drafted rung, and it rewrote stored templated rungs to `end_turn`), "
          "so a truncated draft could not be seen in the replays. *Fixed:* the capture script stores the API's `stop_reason` and no longer rewrites it, and the live path "
          "returns it on each rung result. The stored drafts were not re-captured, so they still carry the constant; their normal completion is inferred from text that "
          "ends cleanly and output below the cap.",
          _cat2_owner_issue(res),
          "13. **The Category 4 capture script rejected answers with zero citations** (`capture_cat4_replays.py::_validate_rung`), which selects the recorded runs by outcome. "
          "*Fixed:* it now checks infrastructure only (every question answered and ended normally, cache written/read, reranker ran); the quality rerun kept every answer "
          f"and found {sum(v['questions_with_zero_citations'] for k, v in res['categories']['cat4']['per_question'].items() if not k.startswith('naive'))} zero-citation answers on the citation rungs.",
          "14. **The Category 4 answer cap truncated answers.** At the app's `max_tokens=2048`, 3 of 64 pilot answers stopped on `max_tokens`, and the live path raises on truncation. "
          + (f"In the rerun at 4,096, {res['categories']['cat4']['call_stats']['synthesis_outputs_above_app_cap_before']}/{res['categories']['cat4']['call_stats']['answers']} answers used more than 2,048 output tokens (extended thinking included). "
             if res["categories"]["cat4"].get("call_stats") else "")
          + "*Fixed:* the app's synthesis cap is now 4,096 and real stop reasons are recorded.",
          "15. **Category 4 BM25 is tuned to these questions.** `retriever.py` adds phrase bonuses for specific terms and values in the 8 test questions and Deccan's contracts, "
          "and the reranker prompt names the clauses the questions ask about, so BM25+rerank recall here is optimistic for unseen questions; with two look-alike suppliers added, "
          "it still dropped to the figures in the quality table.",
          "16. **The Category 4 answer template invites absence claims.** The synthesis prompt's last bullet asks for a \"Required Sign-Off Gate: concrete operational, banking NOC, escrow, "
          "or delisting gate\". When the answering model sees only 5 retrieved chunks, it fills that bullet by stating the documents contain no NOC or escrow gate. "
          + _cat4_absence_issue_text()
          + "The prompt is unchanged here (changing it would change the measured system).",
          "",
          "## Limitations",
          "",
          "- Small samples: 12 items (Category 1), 4 documents, 3 invoices; Category 4 has 24 answers per rung and corpus size (8 questions × 3 sessions); Category 3 has 6 sessions per rung (2 scenarios × 3 repeats) and Category 6 has 15 runs per arm (3 incidents × 5 repeats). Treat percentages as indicative, not statistically robust.",
          "- Category 6 ceiling effect: every arm verified 15/15, so these incidents are too easy to show a quality difference between context designs, and CpO equals cost per run in every arm.",
          "- Category 2 now has a quality measurement: a deterministic fact key plus a single blind LLM judge (`claude-opus-5-5`; rubric with 3 passes per draft and "
          "position-swapped head-to-head comparisons) on one draft per rung per document (12 drafts). Judge repeats measure judge noise, not drafting variance, and no "
          "second judge or human grading cross-checks the judge's taste; the lead hand-verified the serious errors against the sources.",
          "- Category 3 now has a quality measurement: a fixed answer key scored by deterministic string matching (no LLM judge). It checks whether specific IDs, amounts and dates "
          "survive, not whether an answer is helpful, and the recall questions are 6 per scenario (12 in all), each asked once per session.",
          "- Category 4 quality: one blind-grader pass per answer (`claude-opus-5-5`, not a model under test) plus a deterministic answer key; 8 questions on one deal room; "
          "the larger corpus adds two synthetic look-alike suppliers generated by a deterministic transform of Deccan's documents, not real contracts. Grader noise was not "
          "measured (no repeat grading) and no human graded the answers; the lead checked the serious errors' source quotes against the documents.",
          "- Several rungs change more than one lever at once (model + template, caching + step cap + projection), so savings cannot be attributed to individual levers.",
          "- The deck's daily-volume claim (Category 6: 1.5M–10M tokens/dev/day) and its production-scale framing can't be checked from single runs.",
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
