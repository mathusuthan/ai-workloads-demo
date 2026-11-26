"""Category 2 quality scoring: renderer, answer key, number extraction, scoring maths, judge planning/parsing,
resume + budget guard, aggregation and the analysis script. No network."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.archetypes.cat2_drafting import quality_scoring as qs
from app.archetypes.cat3_assistants import scoring as cat3_scoring
from app.archetypes.cat6_swarms.fair_rerun import wilson_interval
from app.data.cat2_fixtures import CAT2_PRESETS

BACKEND = Path(__file__).resolve().parent.parent
PAYLOADS = {p["id"]: p["payload"] for p in CAT2_PRESETS}


@pytest.fixture(scope="module")
def keys():
    return qs.load_quality_keys()


@pytest.fixture(scope="module")
def replays():
    return qs.load_replays()


@pytest.fixture(scope="module")
def det(replays, keys):
    return qs.run_deterministic(replays, keys)


@pytest.fixture(scope="module")
def plan(det):
    return qs.plan_judge_calls(det)


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------------------
# A. Renderer
# --------------------------------------------------------------------------------------------------

SAMPLE_DRAFT = {
    "document_title": "Diwali Day 3 Readout",
    "document_type": "EXECUTIVE_OPS_READOUT",
    "executive_summary": {"headline": "SLA slipped to 86.2%", "narrative": "Backlog  is\n41,800 cages.", "bottom_line_impact": "Exposure $313,330."},
    "key_findings": [{"id": "KF-1", "theme": "Sortation", "quantified_evidence": "Sorter availability 81.4%.", "source_anchor": "[15:33:19] Rohan"}],
    "risk_and_compliance_matrix": [{"domain": "Carrier SLA", "severity": "CRITICAL", "exposure_summary": "$77,330 surcharges.", "mitigation_control": "BlueDart standby."}],
    "action_plan": [{"owner": "VP Fulfillment", "milestone": "Clear backlog.", "target_window": "by 23:59Z", "verification_metric": "Backlog zero."}],
}


def test_render_structured_draft_is_markdown_without_json_or_field_names():
    out = qs.render_structured_draft(SAMPLE_DRAFT)
    assert out.startswith("# Diwali Day 3 Readout\n")
    for heading in ("## Executive Summary", "## Key Findings", "## Risk & Compliance Matrix", "## Action Plan"):
        assert heading in out
    for field in ("quantified_evidence", "source_anchor", "exposure_summary", "mitigation_control", "verification_metric",
                  "target_window", "bottom_line_impact", "document_type", "executive_summary"):
        assert field not in out
    assert not re.search(r'[{}\[\]]"|"\s*:', out)  # no JSON syntax
    assert "Backlog is 41,800 cages." in out  # whitespace collapsed
    assert "### KF-1 · Sortation" in out and "(severity: CRITICAL)" in out
    assert "### VP Fulfillment — by 23:59Z" in out and "- **Milestone:** Clear backlog." in out
    assert "*Executive Ops Readout*" in out
    assert qs.render_structured_draft(SAMPLE_DRAFT) == out  # deterministic


def test_render_tolerates_missing_sections():
    out = qs.render_structured_draft({"document_title": "T", "executive_summary": {"headline": "H"}})
    assert out == "# T\n\n## Executive Summary\n\n**H**\n"


def test_render_draft_dispatch(replays):
    rungs = replays["presets"]["brief-01"]["rungs"]
    unbounded = {"raw_markdown": "# Long draft\n\nProse.", "structured_draft": {"mode": "unbounded_longform_prose", "char_length": 21}}
    assert qs.render_draft(unbounded) == unbounded["raw_markdown"]
    tmpl = qs.render_draft(rungs["sonnet_templated"])
    assert tmpl == qs.render_structured_draft(rungs["sonnet_templated"]["structured_draft"])
    assert '"key_findings"' not in tmpl and "quantified_evidence" not in tmpl


def test_iter_drafts_covers_every_replayed_draft(replays):
    drafts = qs.iter_drafts(replays)
    expected = {(p, r) for p in qs.PRESET_IDS for r in replays["presets"][p]["rungs"] if r in qs.RUNG_IDS}
    assert len(drafts) == len(expected) > 0
    assert {(d["preset_id"], d["rung_id"]) for d in drafts} == expected
    assert all(d["text"].strip() and d["output_tokens"] > 0 for d in drafts)


# --------------------------------------------------------------------------------------------------
# Normalisation / matching reuse
# --------------------------------------------------------------------------------------------------


def test_normaliser_and_matcher_are_the_category3_ones():
    assert qs.normalise_text is cat3_scoring.normalise_text
    assert qs.contains_alternative is cat3_scoring.contains_alternative
    assert qs.wilson_interval is wilson_interval
    n = qs.normalise_text("Backlog **41,800** cages; exposure $313,330 — SLA 86.2%")
    assert "41800" in n and "313330" in n and "-" in n
    assert qs.contains_alternative(n, "41800")
    assert not qs.contains_alternative(qs.normalise_text("418000 cages"), "41800")  # boundary guard
    assert not qs.contains_alternative(qs.normalise_text("11.50%"), "11.5")


def test_score_facts_reports_matched_alternative():
    facts = [
        {"id": "a", "tier": "core", "category": "money", "any_of": ["313330"]},
        {"id": "b", "tier": "detail", "category": "metric", "any_of": ["lane 4", "81.4"]},
        {"id": "c", "tier": "detail", "category": "owner", "any_of": ["ananya"]},
    ]
    rows = qs.score_facts("Exposure **$313,330**; sorter availability 81.4%.", facts)
    assert [(r["fact_id"], r["hit"], r["matched"]) for r in rows] == [("a", True, "313330"), ("b", True, "81.4"), ("c", False, None)]


# --------------------------------------------------------------------------------------------------
# Answer-key invariants
# --------------------------------------------------------------------------------------------------


def test_key_ids_unique_and_fields(keys):
    ids = [f["id"] for f in keys["facts"]]
    assert len(ids) == len(set(ids))
    for f in keys["facts"]:
        assert f["preset_id"] in PAYLOADS
        assert f["tier"] in qs.FACT_TIERS
        assert f["category"] in qs.FACT_CATEGORIES
        assert f["description"].strip() and f["any_of"]
        assert len(set(f["any_of"])) == len(f["any_of"])


def test_key_counts_per_bundle_and_tier(keys):
    c = Counter((f["preset_id"], f["tier"]) for f in keys["facts"])
    for pid in PAYLOADS:
        total = c[(pid, "core")] + c[(pid, "detail")]
        assert 14 <= total <= 18, pid
        assert 6 <= c[(pid, "core")] <= 8, pid


def test_every_evidence_quote_is_verbatim_and_short(keys):
    for f in keys["facts"]:
        q = f["evidence"]["quote"]
        assert len(q) <= 200, f["id"]
        assert q in PAYLOADS[f["preset_id"]], f["id"]


def _variants(keys):
    return {(v["fact_id"], v["added"]): v for v in keys["meta"]["format_variants_added_detail"]}


def test_every_key_alternative_matches_its_own_payload(keys):
    variants = _variants(keys)
    for f in keys["facts"]:
        norm = qs.normalise_text(PAYLOADS[f["preset_id"]])
        for alt in f["any_of"]:
            v = variants.get((f["id"], alt))
            # Dry-pass format variants need not occur literally; the alternative they stand for must.
            target = v["equivalent_to"] if v else alt
            assert qs.contains_alternative(norm, target), (f["id"], alt)


def test_dry_pass_variants_are_recorded_and_same_value(keys):
    meta = keys["meta"]
    detail = meta["format_variants_added_detail"]
    assert meta["format_variants_added_from_dry_pass"] == len(detail)
    by_id = {f["id"]: f for f in keys["facts"]}
    for v in detail:
        f = by_id[v["fact_id"]]
        assert v["added"] in f["any_of"] and v["equivalent_to"] in f["any_of"] and v["added"] != v["equivalent_to"]
        num = lambda s: {x for t in qs.extract_tokens(s) if t["kind"] == "number" for x in t["values"]}
        if num(v["equivalent_to"]):
            assert num(v["added"]) & num(v["equivalent_to"]), v  # numeric variants carry the same value


# --------------------------------------------------------------------------------------------------
# C. Number extraction and ignore rules
# --------------------------------------------------------------------------------------------------


def _tok(s):
    return [(t["kind"], t["text"], t.get("values")) for t in qs.extract_tokens(s)]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("₹1,48,000", [("number", "₹1,48,000", [148000.0])]),
        ("$38.4M", [("number", "$38.4M", [38400000.0])]),
        ("38.4 million", [("number", "38.4 million", [38400000.0])]),
        ("$61,250", [("number", "$61,250", [61250.0])]),
        ("86.2%", [("number", "86.2%", [86.2])]),
        ("41.8k cages", [("number", "41.8k", [41800.0])]),
        ("12.9x", [("number", "12.9x", [12.9])]),
        ("4,850ms", [("number", "4,850ms", [4850.0])]),
        ("~$315k/yr", [("number", "$315k/yr", [315000.0])]),
        ("4.8m", [("number", "4.8m", [4.8])]),  # bare 'm' is not a magnitude without a currency sign
        ("$4.8m", [("number", "$4.8m", [4800000.0])]),
    ],
)
def test_number_values(text, expected):
    assert _tok(text) == expected


def test_times_identifiers_and_dates():
    assert _tok("13:30Z") == [("time", "13:30Z", None)]
    assert qs.extract_tokens("[15:31:04] Ananya")[0]["time"] == "15:31"
    assert [t["kind"] for t in qs.extract_tokens("T+1 Q3 FY2027 UN38.3 KF-1 SLR-77401 ESCROW_HOLD_409")] == ["identifier"] * 7
    d = qs.extract_tokens("by November 15, 2026")[0]
    assert (d["kind"], d["y"], d["m"], d["d"]) == ("date", 2026, 11, 15)
    d = qs.extract_tokens("2026-08-29T04:18:00+05:30")[0]
    assert (d["y"], d["m"], d["d"], d["time"]) == (2026, 8, 29, "04:18")
    assert qs.extract_tokens("16 Nov 2026")[0]["kind"] == "date"
    assert qs.extract_tokens("April 2026")[0]["d"] is None
    assert qs.extract_tokens("Mayor 15")[0]["kind"] == "number"  # month names need a word boundary


def test_ranges_and_signs():
    toks = qs.extract_tokens("$115,000–$180,000")
    assert [t["values"] for t in toks] == [[115000.0], [180000.0]]
    toks = qs.extract_tokens("$115–180K")
    assert toks[0]["values"] == [115.0, 115000.0] and toks[1]["values"] == [180000.0]
    toks = qs.extract_tokens("14%–19%")
    assert [t["values"] for t in toks] == [[14.0], [19.0]] and all(t["sign"] == "" for t in toks)
    t = qs.extract_tokens("a -10.3 pts gap")[0]
    assert t["sign"] == "-" and t["values"] == [10.3]
    t = qs.extract_tokens("(−2.1pp)")[0]
    assert t["sign"] == "-" and t["values"] == [2.1]
    assert qs.extract_tokens("+210%")[0]["sign"] == "+"


def test_word_prefix_split_and_dotted_sections():
    assert _tok("sub-4.2x")[0] == ("number", "4.2x", [4.2])
    assert _tok("trailing-60-day")[0] == ("number", "60-day", [60.0])
    assert _tok("post-12:00Z")[0][0] == "time"
    assert _tok("multi-SKU") == []
    assert _tok("pre-T+7") == [("identifier", "T+7", None)]
    assert [t[1] for t in _tok("3.2.1 x")] == ["3.2"]  # the trailing ".1" is not a number of its own


SRC = """=== BUNDLE ===
meeting_id: NM-WAR-2026-W46-09
date_utc: 2026-11-16T15:30:00Z
[15:31:04] We closed at $38.4M across 612,000 orders. Backlog 41,800 cages; SLA 86.2%; dock release 13:30Z.
Holds of $61,250 before the T+1 cutoff. Plan for Q4 Peak. Gate 3 queues. Day 30 review. Range $115,000–$180,000.
"""


def _cls(draft: str) -> list[tuple[str, str, str | None]]:
    return [(r["text"], r["classification"], r["ignore_reason"]) for r in qs.classify_numbers(draft, SRC)]


def test_classification_in_source_and_not_in_source():
    rows = _cls("GMV 38.4 million, $38,400,000 and $38.4M; backlog 41.8k; SLA 86.2 %; total $374,580.")
    assert rows == [
        ("38.4 million", "in_source", None),
        ("$38,400,000", "in_source", None),
        ("$38.4M", "in_source", None),
        ("41.8k", "in_source", None),
        ("86.2", "in_source", None),
        ("$374,580", "not_in_source", None),
    ]
    assert _cls("release at 13:30Z, deadline 23:59Z") == [("13:30Z", "in_source", None), ("23:59Z", "not_in_source", None)]
    assert _cls("T+1 and T+2") == [("T+1", "in_source", None), ("T+2", "not_in_source", None)]
    assert _cls("Q4 vs Q3") == [("Q4", "in_source", None), ("Q3", "not_in_source", None)]
    # magnitude errors are not masked by the mantissa: $38.4 (no M) is not in the source
    assert _cls("$38.4 GMV") == [("$38.4", "not_in_source", None)]
    # sign is informational; matching is on absolute value
    assert _cls("delta -86.2%") == [("86.2%", "in_source", None)]
    # range left side borrows the right side's magnitude
    assert _cls("$115–180K") == [("$115", "in_source", None), ("180K", "in_source", None)]


def test_ignore_list_numbering():
    draft = "1. Backlog 41,800\n2) SLA 86.2%\n## 3. Risks\n### 3.2 Carrier\n**4.** Owner\n| 5 | row | 8 |\nText 7. here"
    rows = _cls(draft)
    assert rows[:3] == [("1", "ignored", "list_numbering"), ("41,800", "in_source", None), ("2", "ignored", "list_numbering")]
    assert ("3", "ignored", "list_numbering") in rows and ("3.2", "ignored", "list_numbering") in rows
    assert ("4", "ignored", "list_numbering") in rows and ("5", "ignored", "list_numbering") in rows
    assert ("8", "not_in_source", None) in rows and ("7", "not_in_source", None) in rows  # not at line start


def test_ignore_own_labels():
    rows = _cls("### KF-1 · Sortation\nKF-03 and F2. See Finding 2, Risk 3, Section 4, Section 2.4, Section A.1. Gate 3 and Gate 8.")
    got = {(t, c, r) for t, c, r in rows}
    for label in ("KF-1", "KF-03", "F2", "2", "4", "2.4", "A.1"):
        assert (label, "ignored", "own_label") in got, label
    assert ("3", "in_source", None) in got  # "Risk 3" is a label, but "Gate 3" is in the source anyway
    assert ("8", "not_in_source", None) in got  # Gate 8: not a label word, not in source
    # digit runs inside source identifiers count as in source ("W46-09" -> 9): conservative against false flags
    assert _cls("Gate 9") == [("9", "in_source", None)]
    # a label phrase that occurs in the source is not ignored
    assert _cls("the Day 30 review") == [("30", "in_source", None)]


def test_ignore_title_document_id_years_and_dates():
    rows = _cls("# Readout W46 — Day 3 of 2026\nRef NM-WAR-2026-W46-09. On 16 November 2026 (2026) and Nov 17, 2026; in 2031.")
    assert rows[0][2] == "in_title" and all(r[2] == "in_title" for r in rows if "Readout" in r[0] or r[0] in ("W46", "3"))
    got = [(t, c, r) for t, c, r in rows if "in_title" != r]
    assert got == [
        ("NM-WAR-2026-W46-09", "ignored", "document_id"),
        ("16 November 2026", "ignored", "date_in_source"),
        ("2026", "ignored", "year_in_source"),
        ("Nov 17, 2026", "not_in_source", None),
        ("2031", "not_in_source", None),
    ]


def test_numbers_summary_and_ids():
    rows = qs.classify_numbers("1. Total $374,580 vs 41,800 and $1.2M\n", SRC)
    s = qs.numbers_summary(rows)
    assert s == {
        "tokens_extracted": 4, "ignored": 1, "ignored_by_reason": {"list_numbering": 1}, "numeric_tokens": 3,
        "in_source": 1, "not_in_source": 2, "not_in_source_share": 2 / 3,
    }
    nis = qs.not_in_source_list(rows)
    assert [n["id"] for n in nis] == ["N01", "N02"] and [n["text"] for n in nis] == ["$374,580", "$1.2M"]
    assert "$374,580" in nis[0]["snippet"] and len(nis[0]["snippet"]) <= 80 * 2 + 20


def test_real_drafts_numbers_sane(det):
    for c in det["drafts"]:
        s = c["numbers_summary"]
        assert s["numeric_tokens"] == s["in_source"] + s["not_in_source"]
        assert s["tokens_extracted"] == s["numeric_tokens"] + s["ignored"]
        # every "not in source" number value really is absent from the source index
        idx = qs.build_source_index(PAYLOADS[c["preset_id"]])
        for r in c["numbers"]:
            if r["classification"] == "not_in_source" and r["kind"] == "number":
                assert not set(r["values"]) & idx.values


# --------------------------------------------------------------------------------------------------
# Scoring maths
# --------------------------------------------------------------------------------------------------


def test_coverage_summary_maths():
    rows = [
        {"hit": True, "tier": "core", "category": "money"},
        {"hit": False, "tier": "core", "category": "deadline"},
        {"hit": True, "tier": "detail", "category": "money"},
        {"hit": True, "tier": "detail", "category": "cause"},
    ]
    s = qs.coverage_summary(rows, output_tokens=2000)
    assert (s["overall"]["hits"], s["overall"]["total"]) == (3, 4)
    assert (s["core"]["hits"], s["core"]["total"], s["detail"]["hits"]) == (1, 2, 2)
    assert s["by_category"]["money"]["hits"] == 2 and s["by_category"]["owner"]["total"] == 0
    assert s["facts_per_1k_output_tokens"] == pytest.approx(1.5)
    assert s["overall"]["wilson95"] == wilson_interval(3, 4)


def test_deterministic_pooling_consistent(det, keys):
    assert len(det["drafts"]) == len(qs.iter_drafts(qs.load_replays()))
    for rid in det["rungs"]:
        r = det["rungs"][rid]
        cells = [c for c in det["drafts"] if c["rung_id"] == rid]
        if not cells:
            continue
        assert r["coverage"]["overall"]["total"] == len(keys["facts"])
        assert r["coverage"]["overall"]["hits"] == sum(c["coverage"]["overall"]["hits"] for c in cells)
        assert r["output_tokens"]["total"] == sum(c["output_tokens"] for c in cells)
        assert r["cost_per_1k_docs_usd"] == pytest.approx(sum(c["cost_per_1k_docs_usd"] for c in cells) / len(cells))
        assert r["numbers"]["not_in_source"] == sum(c["numbers_summary"]["not_in_source"] for c in cells)
    pf = {p["fact_id"]: p for p in det["per_fact"]}
    assert set(pf) == {f["id"] for f in keys["facts"]}
    assert det["facts_covered_by_no_draft"] == [k for k, v in pf.items() if all(h is False for h in v["hits"].values())]


def test_targets_are_payload_substrings():
    for pid, t in qs.TARGETS.items():
        assert t["deliverable"] in PAYLOADS[pid] and t["reader"] in PAYLOADS[pid]


# --------------------------------------------------------------------------------------------------
# Call planning and blinding
# --------------------------------------------------------------------------------------------------


def test_plan_counts_ids_and_orders(plan, det):
    n = len(det["drafts"])
    present = {(c["preset_id"], c["rung_id"]) for c in det["drafts"]}
    pairs = [(pid, x, y) for pid in qs.PRESET_IDS for x, y in qs.rung_pairs() if (pid, x) in present and (pid, y) in present]
    assert Counter(p["task"] for p in plan) == {"rubric": 3 * n, "pairwise": 2 * len(pairs)}
    ids = [p["call_id"] for p in plan]
    assert len(set(ids)) == len(plan)
    assert [p["call_id"] for p in qs.plan_judge_calls(det)] == ids  # deterministic
    assert "rubric:brief-01:sonnet_templated:r2" in ids
    pw = [p for p in plan if p["task"] == "pairwise"]
    for pid, x, y in pairs:
        fwd = next(p for p in pw if p["call_id"] == qs.pairwise_call_id(pid, x, y, "fwd"))
        rev = next(p for p in pw if p["call_id"] == qs.pairwise_call_id(pid, x, y, "rev"))
        assert (fwd["a_rung"], fwd["b_rung"]) == (x, y) and (rev["a_rung"], rev["b_rung"]) == (y, x)
    rub = Counter((p["preset_id"], p["rung_id"]) for p in plan if p["task"] == "rubric")
    assert set(rub.values()) == {3} and len(rub) == n
    # rubric is repeat-major so a partial run stays balanced
    assert [p["repeat_index"] for p in plan if p["task"] == "rubric"][:n] == [0] * n


def test_rubric_prompt_contents(plan, det):
    p = next(x for x in plan if x["call_id"] == "rubric:brief-01:haiku_templated:r0")
    cell = next(c for c in det["drafts"] if (c["preset_id"], c["rung_id"]) == ("brief-01", "haiku_templated"))
    assert PAYLOADS["brief-01"] in p["user"] and cell["text"].strip() in p["user"]
    assert qs.TARGETS["brief-01"]["reader"] in p["user"]
    assert p["numbers"] == cell["not_in_source"]
    for n in p["numbers"]:
        assert f'{n["id"]}: "{n["text"]}"' in p["user"]
    empty = next(x for x in plan if x["call_id"] == "rubric:brief-01:sonnet_templated:r0")
    assert ("(none)" in empty["user"]) == (not empty["numbers"])
    for anchor in ("factual_accuracy", "coverage", "clarity", "actionability", "concision"):
        block = p["system"].split(anchor + " —", 1)[1].split("\n\n", 1)[0]
        assert "5:" in block and "3:" in block and "1:" in block, anchor
    assert "Quote, do not paraphrase" in p["system"] and "is NOT an error" in p["system"]


def test_blinding_over_every_planned_prompt(plan, det):
    forbidden_numbers = []
    for c in det["drafts"]:
        for k in ("input_tokens", "output_tokens"):
            forbidden_numbers += [str(c[k]), f"{c[k]:,}"]
        forbidden_numbers += [f"{c['cost_usd']:.4f}", f"{c['cost_per_1k_docs_usd']:.2f}"]
    for p in plan:
        prompt = p["system"] + "\n" + p["user"]
        embedded = [PAYLOADS[p["preset_id"]]] + [c["text"] for c in det["drafts"] if c["preset_id"] == p["preset_id"]]
        embedded += [n["snippet"] for n in p.get("numbers", [])]
        assert qs.blinding_violations(prompt, embedded, forbidden_numbers) == [], p["call_id"]
        low = prompt.lower()
        for word in ("claude-", "sonnet", "opus", "anthropic", *qs.RUNG_IDS):
            assert word not in low, (p["call_id"], word)
        # drafts are labelled only Draft / Draft A / Draft B
        labels = set(re.findall(r"<(draft[_a-z]*)>", prompt))
        assert labels == ({"draft"} if p["task"] == "rubric" else {"draft_a", "draft_b"})


def test_both_judge_prompts_are_layout_neutral(plan):
    length_rule = "do not let the draft's length or format influence any dimension other than clarity and concision"
    assert length_rule in qs.RUBRIC_SYSTEM_PROMPT
    for prompt in (qs.RUBRIC_SYSTEM_PROMPT, qs.PAIRWISE_SYSTEM_PROMPT):
        assert qs.LAYOUT_NEUTRAL_INSTRUCTION in prompt
    assert "content requirement" in qs.LAYOUT_NEUTRAL_INSTRUCTION and "prose, bullets or a table" in qs.LAYOUT_NEUTRAL_INSTRUCTION
    assert all(qs.LAYOUT_NEUTRAL_INSTRUCTION in p["system"] for p in plan)


def test_judge_max_tokens_default():
    assert qs.JUDGE_MAX_TOKENS == 8000


def test_lead_rulings_recorded(keys):
    rulings = {(r["fact_id"], r["alternative"]): r for r in keys["meta"]["lead_rulings"]}
    variants = _variants(keys)
    for k in (("r1-delisted-15-skus", "15 delisted"), ("r2-cause-iban-19", "19 third-party iban")):
        assert k in rulings and k in variants and rulings[k]["date"] == "2026-11-25"
    assert keys["meta"]["keys_version"] == "2026-11-25.3"


def test_blinding_detector_catches_leaks():
    leak = "Draft produced by claude-haiku-5-5 (sonnet_templated), 1,853 output tokens, cost $0.02"
    hits = qs.blinding_violations(leak, [], ["1853", "1,853"])
    for w in ("claude", "haiku", "sonnet_templated", "token", "cost", "number:1,853"):
        assert w in hits
    assert qs.blinding_violations("<draft>uses a Haiku gate</draft>", ["uses a Haiku gate"]) == []


# --------------------------------------------------------------------------------------------------
# Fake judge, parsing, resume, budget
# --------------------------------------------------------------------------------------------------


def rubric_obj(numbers, scores=(4, 4, 4, 4, 4), errors=(), verdict="derived_correct"):
    return {
        "factual_errors": list(errors),
        "unsupported_numbers_review": [{"id": n["id"], "verdict": verdict, "reason": "x"} for n in numbers],
        "scores": {d: {"score": s, "justification": "j"} for d, s in zip(qs.DIMENSIONS, scores)},
    }


def pair_obj(pref="A", acc="A", use="A"):
    return {"dimension_preferences": {"accuracy": acc, "usefulness_to_reader": use}, "preferred": pref, "reason": "r"}


class FakeJudge:
    def __init__(self, responder=None, fail_ids=(), stop_reason="end_turn"):
        self.calls = []
        self.responder = responder
        self.fail_ids = set(fail_ids)
        self.stop_reason = stop_reason

    async def __call__(self, *, system, user, schema, max_tokens):
        self.calls.append(user)
        if any(fid in user for fid in self.fail_ids):
            raise RuntimeError("boom")
        if schema is qs.RUBRIC_SCHEMA:
            ids = re.findall(r"^(N\d\d): ", user, re.M)
            obj = self.responder(user) if self.responder else rubric_obj([{"id": i} for i in ids])
        else:
            obj = self.responder(user) if self.responder else pair_obj()
        return qs.JudgeResponse(
            model_id="claude-opus-5-5", stop_reason=self.stop_reason, input_tokens=10_000, output_tokens=2_000,
            thinking_tokens=500, cache_creation_tokens=0, cache_read_tokens=0, latency_ms=1234,
            raw_text=json.dumps(obj), request_id="req_1",
        )


def test_execute_ok_records_everything(plan):
    p = next(x for x in plan if x["task"] == "rubric" and x["numbers"])
    rec = asyncio.run(qs.execute_judge_call(p, judge_call=FakeJudge()))
    assert rec["status"] == "ok" and rec["error_type"] is None
    assert rec["model_id"] == "claude-opus-5-5" and rec["stop_reason"] == "end_turn"
    assert (rec["input_tokens"], rec["output_tokens"], rec["thinking_tokens"], rec["latency_ms"]) == (10_000, 2_000, 500, 1234)
    assert json.loads(rec["raw_text"]) == rec["parsed"]
    assert rec["numbers_reviewed"] == p["numbers"] and rec["prompt_sha256"] == p["prompt_sha256"]
    assert rec["settings"]["max_retries"] == 0 and rec["settings"]["thinking"] == {"type": "adaptive"}


@pytest.mark.parametrize(
    "raw,etype",
    [
        ("not json", "invalid_json"),
        (json.dumps({"scores": {}}), "schema_violation"),
        (json.dumps({**rubric_obj([]), "scores": {d: {"score": 7, "justification": "j"} for d in qs.DIMENSIONS}}), "schema_violation"),
        (json.dumps({**rubric_obj([]), "extra": 1}), "schema_violation"),
    ],
)
def test_parse_rejects_bad_output(raw, etype):
    with pytest.raises(qs.JudgeOutputError) as ei:
        qs.parse_judge_output("rubric", raw, [])
    assert ei.value.error_type == etype


def test_parse_requires_one_review_per_number():
    nums = [{"id": "N01"}, {"id": "N02"}]
    qs.parse_judge_output("rubric", json.dumps(rubric_obj(nums)), nums)
    for bad in (rubric_obj(nums[:1]), rubric_obj(nums + [{"id": "N03"}]), rubric_obj([nums[0], nums[0], nums[1]])):
        with pytest.raises(qs.JudgeOutputError, match="ids mismatch"):
            qs.parse_judge_output("rubric", json.dumps(bad), nums)
    with pytest.raises(qs.JudgeOutputError):
        qs.parse_judge_output("pairwise", json.dumps(pair_obj(pref="C")), [])


def test_execute_error_paths(plan):
    p = next(x for x in plan if x["task"] == "pairwise")
    rec = asyncio.run(qs.execute_judge_call(p, judge_call=FakeJudge(responder=lambda u: {"preferred": "A"})))
    assert rec["status"] == "error" and rec["error_type"] == "schema_violation" and rec["output_tokens"] == 2000
    rec = asyncio.run(qs.execute_judge_call(p, judge_call=FakeJudge(stop_reason="max_tokens")))
    assert rec["status"] == "error" and rec["error_type"] == "stop_reason" and rec["parsed"] is None
    rec = asyncio.run(qs.execute_judge_call(p, judge_call=FakeJudge(fail_ids=["<draft_a>"])))
    assert rec["status"] == "error" and rec["error_type"] == "api_error" and "boom" in rec["error_message"]
    assert rec["input_tokens"] == 0


def test_resume_skips_ok_and_retries_errors(plan):
    existing = [
        {"call_id": plan[0]["call_id"], "status": "ok", "prompt_sha256": plan[0]["prompt_sha256"]},
        {"call_id": plan[1]["call_id"], "status": "error"},
        {"call_id": plan[2]["call_id"], "status": "ok", "prompt_sha256": "different"},
    ]
    pending = qs.select_pending(plan, existing)
    assert [p["call_id"] for p in pending] == [p["call_id"] for p in plan if p["call_id"] not in (plan[0]["call_id"], plan[2]["call_id"])]
    assert qs.stale_ok_records(plan, existing) == [plan[2]["call_id"]]


def test_cost_and_budget_guard():
    assert qs.judge_cost_usd(1_000_000, 1_000_000) == pytest.approx(qs.OPUS_INPUT_PER_1M_USD + qs.OPUS_OUTPUT_PER_1M_USD)
    prior = [{"input_tokens": 100_000, "output_tokens": 10_000, "status": "error"}]  # error records count too
    g = qs.BudgetGuard(1.0, prior)
    assert g.spent_usd == pytest.approx(0.6)
    assert g.try_reserve(0.3) and not g.try_reserve(0.2)
    g.settle(0.3, {"input_tokens": 10_000, "output_tokens": 1_000})
    assert g.spent_usd == pytest.approx(0.66) and g.reserved_usd == 0


def test_run_plan_stops_at_budget(plan):
    written = []
    sub = [p for p in plan if p["task"] == "pairwise"][:6]
    worst = qs.judge_cost_usd(qs.estimate_input_tokens(sub[0]), qs.JUDGE_MAX_TOKENS)
    guard = qs.BudgetGuard(worst * 2.5)
    res = asyncio.run(qs.run_judge_plan(sub, judge_call=FakeJudge(), guard=guard, on_record=written.append, concurrency=1))
    assert res["budget_stopped"] and res["launched"] == len(written) < len(sub)
    assert res["skipped_budget"] == len(sub) - res["launched"]
    assert guard.spent_usd <= guard.max_usd


def test_run_plan_full_with_fake_and_resume(plan, tmp_path):
    out = tmp_path / "j.jsonl"

    def write(rec):
        with out.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")

    fj = FakeJudge(fail_ids=["rubric-will-not-match"])
    res = asyncio.run(qs.run_judge_plan(plan, judge_call=fj, guard=qs.BudgetGuard(1000), on_record=write, concurrency=4))
    assert res["ok"] == len(plan) and not res["budget_stopped"]
    recs = qs.load_judgements(out)
    assert len(recs) == len(plan) and qs.select_pending(plan, recs) == []


def test_estimate_plan(plan):
    est = qs.estimate_plan(plan, chars_per_token=2.25)
    assert est["total"]["calls"] == len(plan)
    n_rubric = sum(1 for p in plan if p["task"] == "rubric")
    assert est["by_task"]["rubric"]["worst_case_output_tokens"] == n_rubric * qs.JUDGE_MAX_TOKENS
    assert est["total"]["worst_case_usd"] >= est["total"]["typical_usd"] > 0


def test_calibrated_chars_per_token(replays):
    assert 1.5 < qs.calibrate_chars_per_token(replays) < 5


def test_real_judge_call_builds_sdk_request(monkeypatch):
    import anthropic

    captured = {}

    class FakeMessages:
        async def create(self, **kw):
            captured.update(kw)

            class U:
                input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens = 11, 22, 0, 0
                output_tokens_details = None

            class B:
                type, text = "text", "{}"

            class R:
                model, stop_reason, usage, content, _request_id = "claude-opus-5-5", "end_turn", U(), [B()], "req"

            return R()

    class FakeClient:
        def __init__(self, **kw):
            captured["client"] = kw
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    call = qs.make_anthropic_judge_call("k")
    resp = asyncio.run(call(system="s", user="u", schema={"type": "object"}, max_tokens=4000))
    assert captured["client"] == {"api_key": "k", "timeout": 300.0, "max_retries": 0}
    assert captured["model"] == "claude-opus-5-5" and captured["max_tokens"] == 4000
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"] == {"format": {"type": "json_schema", "schema": {"type": "object"}}, "effort": "medium"}
    assert (resp.input_tokens, resp.output_tokens, resp.raw_text, resp.request_id) == (11, 22, "{}", "req")


def test_installed_sdk_accepts_output_config_and_adaptive_thinking():
    import inspect

    from anthropic.resources.messages import AsyncMessages
    from anthropic.types import JSONOutputFormatParam, OutputConfigParam, ThinkingConfigAdaptiveParam  # noqa: F401

    params = inspect.signature(AsyncMessages.create).parameters
    assert "output_config" in params and "thinking" in params
    assert {"format", "effort"} <= set(OutputConfigParam.__annotations__)


# --------------------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------------------


def _rub(pid, rid, r, scores, errors=(), numbers=(), verdicts=None):
    nums = [{"id": n, "text": f"t{n}", "snippet": "s"} for n in numbers]
    obj = rubric_obj(nums, scores=scores, errors=errors)
    if verdicts:
        for e, v in zip(obj["unsupported_numbers_review"], verdicts):
            e["verdict"] = v
    return {"call_id": qs.rubric_call_id(pid, rid, r), "task": "rubric", "status": "ok", "preset_id": pid, "rung_id": rid,
            "repeat_index": r, "parsed": obj, "numbers_reviewed": nums, "input_tokens": 1, "output_tokens": 1,
            "model_id": "claude-opus-5-5", "stop_reason": "end_turn", "latency_ms": 5}


def _pw(pid, x, y, order, pref, acc=None, use=None):
    a, b = (x, y) if order == "fwd" else (y, x)
    return {"call_id": qs.pairwise_call_id(pid, x, y, order), "task": "pairwise", "status": "ok", "preset_id": pid,
            "pair": [x, y], "order": order, "a_rung": a, "b_rung": b, "parsed": pair_obj(pref, acc or pref, use or pref),
            "input_tokens": 1, "output_tokens": 1, "model_id": "claude-opus-5-5", "stop_reason": "end_turn", "latency_ms": 5}


def test_majority():
    assert qs.majority(["a", "a", "b"]) == "a"
    assert qs.majority(["a", "b", "c"]) is None
    assert qs.majority(["a", "b"]) is None
    assert qs.majority([]) is None


def test_aggregate_rubric_means_ranges_and_agreement():
    recs = [
        _rub("brief-01", "sonnet_unbounded", 0, (5, 4, 3, 2, 1)),
        _rub("brief-01", "sonnet_unbounded", 1, (4, 4, 3, 2, 3)),
        _rub("brief-01", "sonnet_unbounded", 2, (5, 4, 4, 2, 1)),
        {**_rub("brief-01", "sonnet_unbounded", 2, (1, 1, 1, 1, 1)), "status": "error"},  # error records ignored
    ]
    agg = qs.aggregate_rubric(recs)
    cell = agg["per_draft"]["brief-01|sonnet_unbounded"]["dimensions"]
    assert cell["factual_accuracy"]["scores"] == [5, 4, 5] and cell["factual_accuracy"]["mean"] == pytest.approx(14 / 3)
    assert cell["concision"]["within_1"] is False and cell["clarity"]["within_1"] is True
    rung = agg["rungs"]["sonnet_unbounded"]
    assert (rung["concision"]["min"], rung["concision"]["max"]) == (1, 3)
    assert rung["agreement_within_1"] == {"cells": 5, "within_1": 4, "share": 0.8}
    assert agg["agreement_within_1_overall"]["cells"] == 5


def test_latest_ok_wins():
    a = _rub("brief-01", "haiku_templated", 0, (1, 1, 1, 1, 1))
    b = _rub("brief-01", "haiku_templated", 0, (5, 5, 5, 5, 5))
    agg = qs.aggregate_rubric([a, b])
    assert agg["per_draft"]["brief-01|haiku_templated"]["dimensions"]["coverage"]["scores"] == [5]


def test_aggregate_errors_dedupes_by_quote_similarity():
    e1 = {"claim_quote": "total exposure of $374,580", "problem": "p", "source_quote_or_absent": "ABSENT", "severity": "material"}
    e1b = {**e1, "claim_quote": "Total exposure of **$374,580**", "severity": "minor"}
    e1c = {**e1, "claim_quote": "the total exposure of $374,580 to the board"}
    e2 = {"claim_quote": "18 trailers at Gate 9", "problem": "gate", "source_quote_or_absent": "Bhiwandi Gate 7", "severity": "minor"}
    recs = [
        _rub("brief-01", "sonnet_unbounded", 0, (4,) * 5, errors=[e1, e2]),
        _rub("brief-01", "sonnet_unbounded", 1, (4,) * 5, errors=[e1b]),
        _rub("brief-01", "sonnet_unbounded", 2, (4,) * 5, errors=[e1c]),
    ]
    texts = {("brief-01", "sonnet_unbounded"): "We report a total exposure of $374,580. 18 trailers at Gate 9."}
    agg = qs.aggregate_errors(recs, texts)
    d = agg["per_draft"]["brief-01|sonnet_unbounded"]
    assert d["distinct_errors"] == 2 and d["raw_reports"] == 4
    big = next(e for e in d["errors"] if "374" in e["claim_quote"])
    assert big["repeats_reporting"] == 3 and big["material_votes"] == 2 and big["severity"] == "material"
    assert big["claim_quote_found_in_draft"] is True and big["source_quote_found_in_source"] is None
    small = next(e for e in d["errors"] if "Gate 9" in e["claim_quote"])
    assert small["severity"] == "minor" and small["repeats_reporting"] == 1
    assert small["source_quote_found_in_source"] is True
    assert (d["material"], d["minor"]) == (1, 1)
    assert agg["rungs"]["sonnet_unbounded"]["distinct_errors"] == 2


def test_severity_tie_counts_as_material():
    reports = [
        {"claim_quote": "abc def ghi jkl", "problem": "p", "source_quote_or_absent": "ABSENT", "severity": "material", "repeat_index": 0},
        {"claim_quote": "abc def ghi jkl", "problem": "p", "source_quote_or_absent": "ABSENT", "severity": "minor", "repeat_index": 1},
    ]
    assert qs.dedupe_errors(reports)[0]["severity"] == "material"


def test_aggregate_number_reviews_majority_and_disagreement():
    recs = [
        _rub("reg-01", "sonnet_unbounded", 0, (4,) * 5, numbers=["N01", "N02"], verdicts=["derived_correct", "derived_incorrect"]),
        _rub("reg-01", "sonnet_unbounded", 1, (4,) * 5, numbers=["N01", "N02"], verdicts=["derived_correct", "not_a_claim"]),
        _rub("reg-01", "sonnet_unbounded", 2, (4,) * 5, numbers=["N01", "N02"], verdicts=["derived_correct", "not_in_source_unverifiable"]),
    ]
    agg = qs.aggregate_number_reviews(recs)
    d = agg["per_draft"]["reg-01|sonnet_unbounded"]
    items = {i["id"]: i for i in d["items"]}
    assert items["N01"]["majority"] == "derived_correct" and items["N01"]["unanimous"]
    assert items["N02"]["majority"] == "no_majority" and not items["N02"]["unanimous"]
    assert items["N02"]["text"] == "tN02" and items["N02"]["repeats"] == [0, 1, 2]
    assert d["majority_counts"]["derived_correct"] == 1 and d["majority_counts"]["no_majority"] == 1
    assert d["disagreements"] == 1 and agg["rungs"]["sonnet_unbounded"]["reviewed"] == 2


def test_aggregate_pairwise_matrix_and_position_consistency():
    U, S, H = qs.RUNG_IDS
    recs = [
        _pw("brief-01", U, S, "fwd", "A"),  # U wins (shown as A)
        _pw("brief-01", U, S, "rev", "B"),  # U wins (shown as B) -> consistent
        _pw("brief-01", U, H, "fwd", "A"),  # U wins
        _pw("brief-01", U, H, "rev", "A"),  # H wins (position A both times) -> inconsistent
        _pw("brief-01", S, H, "fwd", "tie", acc="A", use="B"),
        _pw("brief-01", S, H, "rev", "tie", acc="B", use="B"),
    ]
    agg = qs.aggregate_pairwise(recs)
    o = agg["overall"]
    assert o["wins"][U][S] == 2 and o["wins"][S][U] == 0
    assert o["wins"][U][H] == 1 and o["wins"][H][U] == 1
    assert o["ties"][f"{S}|{H}"] == 2
    pc = o["position_consistency"]
    assert (pc["pairs_with_both_orders"], pc["consistent"]) == (3, 2) and pc["share"] == pytest.approx(2 / 3)
    assert pc["inconsistent"] == [{"preset_id": "brief-01", "pair": [U, H], "fwd": U, "rev": H}]
    assert o["decisive_calls"] == 4 and o["share_decisive_choosing_position_a"] == pytest.approx(3 / 4)
    acc = agg["accuracy"]
    assert acc["wins"][S][H] == 2 and acc["position_consistency"]["consistent"] == 2  # S picked in both orders
    use = agg["usefulness_to_reader"]
    assert use["wins"][H][S] == 1 and use["wins"][S][H] == 1 and use["position_consistency"]["consistent"] == 1


def test_summarise_with_and_without_judge(det):
    assert qs.summarise(det, None)["judge"] is None
    recs = [_rub("brief-01", "sonnet_unbounded", 0, (4,) * 5), {"call_id": "x", "task": "rubric", "status": "error",
            "error_type": "api_error", "input_tokens": 0, "output_tokens": 0}]
    s = qs.summarise(det, recs)
    assert s["judge"]["data_quality"]["ok_calls"] == 1 and s["judge"]["data_quality"]["error_records"] == 1


# --------------------------------------------------------------------------------------------------
# Scripts
# --------------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------------
# App summary (replays/cat2_quality_summary.json)
# --------------------------------------------------------------------------------------------------


def test_action_item_flags_matches_heading_owner_and_window():
    draft = {"action_plan": [
        {"owner": "Payments Engineering", "target_window": "Within 30 days"},
        {"owner": "Legal", "target_window": "Q3"},
        {"owner": "Treasury Operations", "target_window": "By 2026-12-01"},
    ]}
    errors = [
        {"claim_quote": "Payments Engineering — Within 30 days", "severity": "material"},  # heading, em dash
        {"claim_quote": "Treasury Operations owns the hold release", "severity": "minor"},  # contains owner (>= 8 chars)
        {"claim_quote": "Legal", "severity": "material"},  # inside heading "legal - q3"
    ]
    out = qs.action_item_flags(draft, errors)
    assert (out["total"], out["flagged"], out["flagged_serious"]) == (3, 3, 2)
    assert [r["serious"] for r in out["items"]] == [True, True, False]
    assert qs.action_item_flags(draft, [{"claim_quote": "unrelated sentence", "severity": "material"}])["flagged"] == 0
    assert qs.action_item_flags({"key_findings": []}, errors) is None


def test_deterministic_quality_for_text_live_draft(replays):
    pid, rid = "reg-02", "haiku_templated"
    text = qs.render_draft(replays["presets"][pid]["rungs"][rid])
    q = qs.deterministic_quality_for_text(text, PAYLOADS[pid], pid)
    cell = json.loads((BACKEND / "replays" / "cat2_quality_summary.json").read_text())["presets"][pid]["rungs"][rid]
    assert q["facts"]["core_facts"] == cell["core_facts"] and q["facts"]["detail_facts"] == cell["detail_facts"]
    assert q["numbers"]["not_in_source"] == cell["numbers"]["not_in_source"]
    assert [i["text"] for i in q["numbers"]["items"]] == [i["text"] for i in cell["numbers"]["items"]]
    custom = qs.deterministic_quality_for_text("Revenue rose 12% to $4.1M.", "Revenue rose 12%.", None)
    assert custom["facts"] is None and [i["text"] for i in custom["numbers"]["items"]] == ["$4.1M"]
