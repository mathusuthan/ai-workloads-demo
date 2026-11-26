"""Category 2 experiment (unbounded long-form draft vs section template with length caps, Sonnet 5.5 and Haiku 5.5):
prompts, schema, planning, resume/budget, field classifier, judge planning, blinding, analysis, app summary, golden
builder and record pruning. No network."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.archetypes.cat2_drafting import not_stated_experiment as ns
from app.archetypes.cat2_drafting import quality_scoring as qs
from app.archetypes.cat2_drafting.prompts import get_templated_draft_system_prompt, get_unbounded_draft_system_prompt
from app.archetypes.cat2_drafting.schemas import STRUCTURED_DRAFT_JSON_SCHEMA
from app.core.anthropic_service import AnthropicRawResult
from app.data.cat2_fixtures import CAT2_PRESETS

BACKEND = Path(__file__).resolve().parent.parent
PAYLOADS = {p["id"]: p["payload"] for p in CAT2_PRESETS}
SUB_TASKS = sorted({p["sub_task"] for p in CAT2_PRESETS})
FILLER = "Appendix note: the background, methodology and historical context are restated here in full detail."


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def replays():
    return qs.load_replays()


@pytest.fixture(scope="module")
def keys():
    return qs.load_quality_keys()


# --------------------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------------------


class FakeDrafter:
    """Template arm: the stored repeat-0 template draft for the bundle/model. Unbounded arm (schema None): that
    draft rendered as prose plus filler paragraphs (a long free-text draft)."""

    def __init__(self, replays: dict[str, Any], *, truncate_ids=(), fail_ids=()) -> None:
        self.replays = replays
        self.calls: list[dict[str, Any]] = []
        self.truncate = set(truncate_ids)
        self.fail = set(fail_ids)
        self.by_payload = {p["payload"]: p["id"] for p in CAT2_PRESETS}

    async def __call__(self, *, system: str, payload: str, schema: dict[str, Any] | None, model_tier: str, max_tokens: int) -> AnthropicRawResult:
        pid = self.by_payload[payload]
        m = "sonnet" if "sonnet" in model_tier else "haiku"
        arm = ns.ARM_TEMPLATE if schema is not None else ns.ARM_UNBOUNDED
        n = sum(1 for c in self.calls if (c["pid"], c["m"], c["arm"]) == (pid, m, arm))
        self.calls.append({"pid": pid, "m": m, "arm": arm, "schema": schema, "max_tokens": max_tokens, "system": system})
        key = ns.draft_key(pid, m, arm, n)
        if key in self.fail:
            raise RuntimeError("overloaded")
        r = self.replays["presets"][pid]["rungs"][f"{m}_templated"]
        sd = copy.deepcopy(r["structured_draft"])
        if arm == ns.ARM_TEMPLATE:
            raw, out_tok = json.dumps(sd), int(r["output_tokens"])
        else:
            raw = qs.render_structured_draft(sd) + "\n\n" + "\n\n".join([FILLER] * 40)
            sd, out_tok = {"mode": "unbounded_longform_prose", "char_length": len(raw)}, 4800
        stop = "end_turn"
        if key in self.truncate:
            raw, sd, stop = raw[: len(raw) // 2], {}, "max_tokens"
        return AnthropicRawResult(model_tier, 900, int(r["input_tokens"]), out_tok, 0, 0, raw, sd,
                                  request_params={"max_tokens": max_tokens}, stop_reason=stop, thinking_tokens=0)


def rubric_obj(ids, scores=(4, 4, 4, 4, 4), errors=()):
    return {
        "factual_errors": list(errors),
        "unsupported_numbers_review": [{"id": i, "verdict": "not_in_source_unverifiable", "reason": "x"} for i in ids],
        "scores": {d: {"score": s, "justification": "j"} for d, s in zip(qs.DIMENSIONS, scores)},
    }


def pair_obj(pref="A", acc="A", use="A"):
    return {"dimension_preferences": {"accuracy": acc, "usefulness_to_reader": use}, "preferred": pref, "reason": "r"}


class FakeJudge:
    def __init__(self, responder=None) -> None:
        self.calls: list[str] = []
        self.responder = responder

    async def __call__(self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> qs.JudgeResponse:
        self.calls.append(user)
        if schema is qs.RUBRIC_SCHEMA:
            ids = re.findall(r"^(N\d\d): ", user, re.M)
            obj = self.responder(user, ids) if self.responder else rubric_obj(ids)
        else:
            obj = self.responder(user, None) if self.responder else pair_obj()
        return qs.JudgeResponse(model_id="claude-opus-5-5", stop_reason="end_turn", input_tokens=9000, output_tokens=1500,
                                thinking_tokens=0, cache_creation_tokens=0, cache_read_tokens=0, latency_ms=10, raw_text=json.dumps(obj))


def _make_drafts(replays, plan=None, **kw) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    asyncio.run(ns.run_draft_plan(plan or ns.plan_drafts(), draft_call=FakeDrafter(replays, **kw), guard=ns.CostGuard(100),
                                  on_record=recs.append, replays=replays, concurrency=1))
    return recs


def _template_only(replays) -> list[dict[str, Any]]:
    return _make_drafts(replays, [p for p in ns.plan_drafts() if p["arm"] == ns.ARM_TEMPLATE])


# --------------------------------------------------------------------------------------------------
# Prompts and schema
# --------------------------------------------------------------------------------------------------


def test_action_plan_rule_is_part_of_the_app_template():
    assert ns.ADDED_INSTRUCTION == (
        "For each action-plan item, give the owner and the time window only if the source states them. "
        "If the source does not name an owner, or gives no date or time window, write exactly `Not stated in source` "
        "in that field. Never supply an owner, team, date or deadline the source does not give."
    )
    assert ns.NOT_STATED == "Not stated in source"
    for st in SUB_TASKS:
        assert get_templated_draft_system_prompt(st).count(ns.ADDED_INSTRUCTION) == 1
        assert ns.ADDED_INSTRUCTION not in get_unbounded_draft_system_prompt(st)


@pytest.mark.parametrize("sub_task", SUB_TASKS)
def test_each_arm_uses_the_app_prompt(sub_task):
    assert ns.system_prompt_for(ns.ARM_UNBOUNDED, sub_task) == get_unbounded_draft_system_prompt(sub_task)
    assert ns.system_prompt_for(ns.ARM_TEMPLATE, sub_task) == get_templated_draft_system_prompt(sub_task)
    with pytest.raises(ValueError):
        ns.system_prompt_for("other", sub_task)


def test_schema_only_on_the_template_arm():
    snapshot = json.dumps(STRUCTURED_DRAFT_JSON_SCHEMA, sort_keys=True)
    assert ns.schema_for(ns.ARM_TEMPLATE) is STRUCTURED_DRAFT_JSON_SCHEMA and ns.schema_for(ns.ARM_UNBOUNDED) is None
    item = STRUCTURED_DRAFT_JSON_SCHEMA["properties"]["action_plan"]["items"]
    assert {"owner", "target_window"} <= set(item["required"])
    plan = ns.plan_drafts()
    assert {p["schema_sha256"] for p in plan if p["arm"] == ns.ARM_UNBOUNDED} == {None}
    assert len({p["schema_sha256"] for p in plan if p["arm"] == ns.ARM_TEMPLATE}) == 1
    assert json.dumps(STRUCTURED_DRAFT_JSON_SCHEMA, sort_keys=True) == snapshot
    with pytest.raises(ValueError):
        ns.schema_for("other")


def test_recorded_template_drafts_were_made_with_the_current_app_prompt():
    if not ns.DRAFTS_PATH.is_file():
        pytest.skip("experiment drafts not present")
    recs = [r for r in ns.load_jsonl(ns.DRAFTS_PATH) if r.get("status") == "ok" and r.get("arm") == ns.ARM_TEMPLATE]
    assert len({r["draft_id"] for r in recs}) == 24
    schema_sha = hashlib.sha256(json.dumps(STRUCTURED_DRAFT_JSON_SCHEMA, sort_keys=True).encode("utf-8")).hexdigest()
    for r in recs:
        assert r["system_sha256"] == hashlib.sha256(get_templated_draft_system_prompt(r["sub_task"]).encode("utf-8")).hexdigest(), r["draft_id"]
        assert r["schema_sha256"] == schema_sha and r["max_tokens"] == 3000
    assert ns.stale_draft_records(ns.plan_drafts(), ns.load_jsonl(ns.DRAFTS_PATH)) == []
    assert {r.get("arm") for r in ns.load_jsonl(ns.DRAFTS_PATH)} <= set(ns.ARMS)


# --------------------------------------------------------------------------------------------------
# Draft planning, estimate, resume, budget guard
# --------------------------------------------------------------------------------------------------


def test_draft_plan_is_48_balanced_and_deterministic():
    plan = ns.plan_drafts()
    assert len(plan) == 48 and len({p["draft_id"] for p in plan}) == 48
    assert [p["draft_id"] for p in plan] == [p["draft_id"] for p in ns.plan_drafts()]
    for field, n in (("arm", 24), ("model_key", 24), ("preset_id", 12), ("repeat_index", 16)):
        assert set(Counter(p[field] for p in plan).values()) == {n}, field
    assert set(Counter((p["preset_id"], p["model_key"], p["arm"]) for p in plan).values()) == {3}
    assert {p["repeat_index"] for p in plan[:16]} == {0}  # repeat-major
    assert plan[0]["draft_id"] == "draft:brief-01:sonnet:unbounded:r0"
    assert plan[1]["draft_id"] == "draft:brief-01:sonnet:template_not_stated:r0"
    assert {p["model_tier"] for p in plan} == {"claude-sonnet-5-5", "claude-haiku-5-5"}
    assert {(p["arm"], p["max_tokens"]) for p in plan} == {(ns.ARM_UNBOUNDED, 8000), (ns.ARM_TEMPLATE, 3000)}
    assert set(ns.APP_RUNG.values()) == {"sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated"}


def test_draft_estimate_uses_the_basis_constants_and_caps():
    plan = ns.plan_drafts()
    u, t = plan[0], plan[1]
    eu, et = ns.estimate_draft(u), ns.estimate_draft(t)
    assert (eu["input_tokens"], eu["typical_output_tokens"]) == ns.UNBOUNDED_ESTIMATE_TOKENS["brief-01"]
    assert (et["input_tokens"], et["typical_output_tokens"]) == ns.TEMPLATE_ESTIMATE_TOKENS["brief-01"]
    assert eu["worst_case_usd"] == pytest.approx((eu["input_tokens"] * 2.0 + 8000 * 10.0) / 1e6)
    unb = ns.estimate_draft_plan([p for p in plan if p["arm"] == ns.ARM_UNBOUNDED])["total"]
    assert unb["drafts"] == 24 and 0 < unb["typical_usd"] < unb["worst_case_usd"] < ns.DEFAULT_DRAFT_MAX_USD


def test_drafting_keeps_truncated_records_errors_and_resumes(replays):
    trunc = ns.draft_key("reg-01", "sonnet", ns.ARM_UNBOUNDED, 0)
    fail = ns.draft_key("brief-02", "haiku", ns.ARM_TEMPLATE, 1)
    drafter = FakeDrafter(replays, truncate_ids={trunc}, fail_ids={fail})
    recs: list[dict[str, Any]] = []
    res = asyncio.run(ns.run_draft_plan(ns.plan_drafts(), draft_call=drafter, guard=ns.CostGuard(100), on_record=recs.append,
                                        replays=replays, concurrency=1))
    assert (res["ok"], res["error"], res["truncated"]) == (47, 1, 1)
    for c in drafter.calls:
        assert (c["max_tokens"], c["schema"]) == ((3000, STRUCTURED_DRAFT_JSON_SCHEMA) if c["arm"] == ns.ARM_TEMPLATE else (8000, None))
    t = next(r for r in recs if r["draft_key"] == trunc)
    assert t["status"] == "ok" and t["truncated"] is True and t["stop_reason"] == "max_tokens"
    assert t["raw_text"] and t["output_tokens"] > 0  # kept, billed tokens recorded
    u = next(r for r in recs if r["draft_key"] == ns.draft_key("brief-01", "haiku", ns.ARM_UNBOUNDED, 0))
    assert u["parse_ok"] is True and u["schema_sha256"] is None and FILLER in u["raw_text"]
    e = next(r for r in recs if r["draft_key"] == fail)
    assert e["status"] == "error" and "overloaded" in e["error_message"]
    assert [p["draft_key"] for p in ns.select_pending_drafts(ns.plan_drafts(), recs)] == [fail]
    assert ns.stale_draft_records(ns.plan_drafts(), recs) == []
    tampered = [{**recs[0], "system_sha256": "x"}]
    assert ns.stale_draft_records(ns.plan_drafts(), tampered) == [recs[0]["draft_id"]]


def test_budget_guard_counts_existing_spend_and_stops_launching(replays):
    plan = ns.plan_drafts()
    worst = ns.estimate_draft(plan[0])["worst_case_usd"]
    recs: list[dict[str, Any]] = []
    res = asyncio.run(ns.run_draft_plan(plan[:4], draft_call=FakeDrafter(replays), guard=ns.CostGuard(worst * 0.5),
                                        on_record=recs.append, replays=replays))
    assert res["launched"] == 0 and res["skipped_budget"] == 4 and res["budget_stopped"] and recs == []
    existing = [{"model_id": "claude-sonnet-5-5", "input_tokens": 5000, "output_tokens": 2000}]
    g = ns.CostGuard(1.0, existing)
    assert g.spent_usd == pytest.approx((5000 * 2 + 2000 * 10) / 1e6)
    assert g.try_reserve(0.5) and not g.try_reserve(0.5)


# --------------------------------------------------------------------------------------------------
# Field classifier
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pid", "value", "expected"),
    [
        ("brief-01", "Ananya Deshmukh", "supported"),  # source-named owner
        ("brief-01", "Ananya Deshmukh, VP Fulfillment and Linehaul Operations", "supported"),  # 'and' for the source's '&'
        ("brief-02", "Siddharth Rao and Nadia Jenkins", "supported"),  # two source-named people
        ("brief-02", "NovaMart Catalog Engineering", "supported"),
        ("reg-02", "Payments Engineering", "unsupported"),  # invented team
        ("reg-02", "Treasury Operations and Compliance", "unsupported"),  # 'Compliance' alone does not make the team
        ("reg-01", "Customer Safety Operations", "unsupported"),
        ("reg-01", "Management", "supported"),  # the source says "Management commits ..." (name present; attribution is the judge's job)
        ("reg-02", "Management", "unsupported"),  # not in this source
        ("reg-02", "the payments team", "unsupported"),  # no capitalised name
        ("reg-02", "Not stated in source", "not_stated"),
        ("reg-02", "not stated in source", "not_stated"),
        ("reg-02", "NOT STATED IN SOURCE.", "not_stated"),
        ("reg-02", "`Not stated in source`", "not_stated"),
        ("reg-02", '"Not stated in source"', "not_stated"),
        ("reg-02", "Not stated in the source", "unsupported"),
        ("reg-02", "Not stated in source (Treasury Operations)", "unsupported"),
    ],
)
def test_owner_classifier(pid, value, expected):
    assert ns.classify_owner(value, PAYLOADS[pid])["class"] == expected


@pytest.mark.parametrize(
    ("pid", "value", "expected"),
    [
        ("brief-02", "By January 10, 2027", "supported"),  # date present in the source
        ("reg-01", "By November 15, 2026", "supported"),
        ("brief-01", "By 17:00Z 16 Nov 2026", "supported"),  # source has 17:00Z and the ISO date 2026-11-16
        ("brief-01", "By 17:00Z 18 Nov 2026", "unsupported"),  # a date the source does not give
        ("brief-02", "Before February 15, 2027 go-live", "supported"),  # source gives "February 15" without a year
        ("reg-02", "Within 30 days", "unsupported"),  # invented
        ("brief-02", "Within 30 days", "supported"),  # brief-02 says "30-day" (token present; the rule is token-level)
        ("brief-02", "Q1 2027", "unsupported"),  # source says Q1 FY2027
        ("brief-02", "Q1 FY2027", "supported"),
        ("reg-02", "Q1 2027", "unsupported"),
        ("reg-01", "Ongoing through Q4 FY2026 audit checkpoint", "unsupported"),  # source period is Q3 FY2026
        ("reg-01", "Ongoing; review at next quarterly audit", "unsupported"),  # no date or duration at all
        ("reg-02", "Not stated in source", "not_stated"),
        ("reg-02", "not stated in source.", "not_stated"),
        ("reg-02", "Not Stated In Source", "not_stated"),
        ("reg-02", "not-stated-in-source", "not_stated"),
        ("reg-02", "Not stated in source (target Q1)", "unsupported"),
    ],
)
def test_window_classifier(pid, value, expected):
    got = ns.classify_window(value, PAYLOADS[pid])
    assert got["class"] == expected, got


def test_time_expressions_canonicalise_dates_durations_and_quarters():
    ex = {e["kind"]: e["key"] for e in ns.time_expressions("By January 10, 2027; within 48 business hours; Q1 FY27; 16 Nov; T+3; Week 46")}
    assert ex["mdy"] == ("date", 1, 10, 2027) and ex["dmy"] == ("date", 11, 16, None)
    assert ex["duration"] == ("duration", 48.0, "business", "hour") and ex["quarter"] == ("quarter", "q1", True, 2027)
    assert ex["t_plus"] == ("tplus", 3) and ex["week"] == ("week", 46)
    assert ns.time_expressions("24-hour")[0]["key"] == ns.time_expressions("24 hours")[0]["key"]


def test_action_items_classified_with_nearest_source_text():
    sd = {"action_plan": [{"action": "a", "owner": "Payments Engineering", "target_window": "Within 30 days"},
                          {"action": "b", "owner": "Not stated in source", "target_window": "Not stated in source"}]}
    items = ns.classify_action_items(sd, PAYLOADS["reg-02"])
    assert [(i["owner_class"], i["window_class"]) for i in items] == [("unsupported", "unsupported"), ("not_stated", "not_stated")]
    near = items[0]["owner_nearest_source"]
    assert near and any(near.rstrip("…") in line or line.startswith(near.rstrip("…")) for line in PAYLOADS["reg-02"].splitlines())
    assert items[1]["owner_nearest_source"] is None
    assert ns.classify_action_items({"executive_summary": {}}, PAYLOADS["reg-02"]) == []
    assert ns.classify_action_items({"mode": "unbounded_longform_prose"}, PAYLOADS["reg-02"]) == []


# --------------------------------------------------------------------------------------------------
# Judge planning and blinding
# --------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scored(replays, keys):
    return ns.score_drafts(_make_drafts(replays), keys)


@pytest.fixture(scope="module")
def jplan(scored):
    return ns.plan_judge_calls(scored)


def test_judge_plan_counts_orders_and_matching(jplan):
    assert len(jplan) == 96 and len({p["call_id"] for p in jplan}) == 96
    assert Counter(p["meta"]["comparison"] for p in jplan) == {"rubric": 48, ns.COMPARISON: 48}
    assert ns.planned_pairwise_calls() == 48
    rub = [p for p in jplan if p["task"] == "rubric"]
    assert all(p["system"] == qs.RUBRIC_SYSTEM_PROMPT and p["schema"] is qs.RUBRIC_SCHEMA for p in rub)
    pw = [p for p in jplan if p["task"] == "pairwise"]
    assert all(p["system"] == qs.PAIRWISE_SYSTEM_PROMPT and p["schema"] is qs.PAIRWISE_SCHEMA for p in pw)
    units: dict[tuple, list] = {}
    for p in pw:
        units.setdefault((p["preset_id"], p["meta"]["model_key"], p["meta"]["draft_repeat"]), []).append(p)
    assert len(units) == 24
    for (pid, m, k), ps in units.items():
        assert sorted(p["order"] for p in ps) == ["fwd", "rev"]
        fwd, rev = sorted(ps, key=lambda p: p["order"])
        assert fwd["a_rung"] == ns.ARM_TEMPLATE and rev["b_rung"] == ns.ARM_TEMPLATE and fwd["b_rung"] == rev["a_rung"] == ns.ARM_UNBOUNDED
        assert fwd["meta"]["draft_keys"] == [ns.draft_key(pid, m, ns.ARM_TEMPLATE, k), ns.draft_key(pid, m, ns.ARM_UNBOUNDED, k)]


def test_judge_plan_leaves_out_calls_whose_drafts_are_missing(replays, keys):
    plan = ns.plan_judge_calls(ns.score_drafts(_template_only(replays), keys))
    assert Counter(p["meta"]["comparison"] for p in plan) == {"rubric": 24}


def test_blinding_holds_over_every_planned_prompt(jplan, scored):
    assert ns.blinding_report(jplan, scored) == {}
    for p in jplan:
        low = (p["system"] + p["user"]).lower()
        for w in ("template_not_stated", "unbounded_longform", "claude-"):
            assert w not in low, (p["call_id"], w)


def test_blinding_catches_planted_leaks(jplan, scored):
    p = next(x for x in jplan if x["task"] == "pairwise")
    for leak in ("\n(arm: template_not_stated)", "\nDraft A came from Haiku.", f"\n{scored[p['meta']['draft_keys'][1]]['output_tokens']} tokens"):
        bad = ns.blinding_report([{**p, "user": p["user"] + leak}], scored)
        assert p["call_id"] in bad, leak


def test_judge_records_carry_baseline_settings(jplan):
    rec = asyncio.run(qs.execute_judge_call(jplan[0], judge_call=FakeJudge()))
    assert rec["status"] == "ok" and rec["judge_model_requested"] == qs.JUDGE_MODEL
    assert rec["settings"] == {"max_tokens": qs.JUDGE_MAX_TOKENS, "thinking": dict(qs.JUDGE_THINKING), "effort": qs.JUDGE_EFFORT,
                               "timeout_s": qs.JUDGE_TIMEOUT_S, "max_retries": 0}


# --------------------------------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------------------------------


def _judge_all(jplan) -> list[dict[str, Any]]:
    """Rubric: 3/4/5/3/4 with one planted serious error; pairwise: the template draft wins in both orders."""
    meta = {p["call_id"]: p["meta"] for p in jplan}
    order = {p["user"]: p["order"] for p in jplan if p["task"] == "pairwise"}

    def responder(user, ids):
        if ids is None:
            c = "A" if order[user] == "fwd" else "B"
            return pair_obj(c, c, c)
        err = {"claim_quote": FILLER[:40], "problem": "not in the source", "source_quote_or_absent": "ABSENT", "severity": "material"}
        return rubric_obj(ids, scores=(3, 4, 5, 3, 4), errors=[err] if FILLER in user else [])

    recs: list[dict[str, Any]] = []

    def on_record(r):
        r["meta"] = meta[r["call_id"]]
        recs.append(r)

    asyncio.run(qs.run_judge_plan(jplan, judge_call=FakeJudge(responder), guard=qs.BudgetGuard(1e6), on_record=on_record, concurrency=8))
    return recs


def test_analysis_without_and_with_judge(replays, jplan):
    drafts = _make_drafts(replays)
    s0 = ns.analyse(drafts, None)
    assert s0["judge_data_quality"] is None and s0["pairwise"]["status"] == "pending" and s0["pairwise"]["all"] is None
    assert {g["status"] for g in s0["groups"].values()} == {"ok"} and s0["groups"][f"{ns.ARM_UNBOUNDED}|sonnet"]["rubric"] is None
    assert s0["groups"][f"{ns.ARM_UNBOUNDED}|haiku"]["action_items"] == 0  # free text has no action-plan fields
    md0 = ns.render_markdown(s0)
    assert "## Head-to-head: template vs unbounded" in md0 and "run pending" in md0

    s = ns.analyse(drafts, _judge_all(jplan))
    assert s["judge_data_quality"]["ok_calls"] == 96
    gu, gt = s["groups"][f"{ns.ARM_UNBOUNDED}|haiku"], s["groups"][f"{ns.ARM_TEMPLATE}|haiku"]
    assert gu["rubric"]["factual_accuracy"]["mean"] == 3 and gu["judged_drafts"] == 12
    assert gu["serious_per_draft"]["mean"] == 1 and gt["serious_per_draft"]["mean"] == 0  # the planted error is in the filler
    a = s["pairwise"]["all"]["overall"]
    assert s["pairwise"]["status"] == "ok" and (a["template_wins"], a["unbounded_wins"], a["ties"]) == (48, 0, 0)
    assert a["position_consistency"] == {"units_with_both_orders": 24, "consistent": 24}
    assert set(s["pairwise"]["by_model"]) == {"sonnet", "haiku"} and s["pairwise"]["by_model"]["haiku"]["calls"] == 24
    assert any(e["claim_quote"] == FILLER[:40] for e in s["review"]["serious_errors"])
    md = ns.render_markdown(s)
    for section in ("## Head-to-head: template vs unbounded", "## By document", "## For lead review", "### Field rules"):
        assert section in md, section
    json.dumps(s)


def test_analysis_with_only_the_template_drafts_marks_the_unbounded_cells_pending(replays):
    s = ns.analyse(_template_only(replays), None)
    assert s["groups"][f"{ns.ARM_UNBOUNDED}|sonnet"]["status"] == "pending" and s["groups"][f"{ns.ARM_TEMPLATE}|sonnet"]["status"] == "ok"
    assert len(s["drafts_data_quality"]["missing_drafts"]) == 24
    assert ns.render_markdown(s).count("run pending") >= 2


def test_analysis_script_with_and_without_judge_file(tmp_path, replays, jplan):
    drafts_path, j_path = tmp_path / "drafts.jsonl", tmp_path / "j.jsonl"
    drafts_path.write_text("".join(json.dumps(r) + "\n" for r in _make_drafts(replays)))
    mod = _load_script("analyze_cat2_experiment")
    md = tmp_path / "out.md"
    assert mod.main(["--drafts", str(drafts_path), "--judgements", str(tmp_path / "missing.jsonl"), "--out-md", str(md)]) == 0
    assert json.loads(md.with_suffix(".json").read_text())["pairwise"]["all"] is None
    j_path.write_text("".join(json.dumps(r) + "\n" for r in _judge_all(jplan)))
    assert mod.main(["--drafts", str(drafts_path), "--judgements", str(j_path), "--out-md", str(md)]) == 0
    assert json.loads(md.with_suffix(".json").read_text())["judge_data_quality"]["ok_calls"] == 96


# --------------------------------------------------------------------------------------------------
# CLI and the app calls
# --------------------------------------------------------------------------------------------------


def test_cli_dry_runs_make_no_calls(tmp_path, monkeypatch, capsys, replays):
    import anthropic

    def boom(*a, **k):
        raise AssertionError("dry run must not build a client")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", boom)
    mod = _load_script("cat2_not_stated_run")
    d = tmp_path / "d.jsonl"
    assert mod.main(["draft", "--dry-run", "--out", str(d), "--show", "2"]) == 0
    out = capsys.readouterr().out
    assert "Planned 48 drafts" in out and "Dry run: no API calls made." in out and not d.exists()
    d.write_text("".join(json.dumps(r) + "\n" for r in _template_only(replays)))
    assert mod.main(["draft", "--dry-run", "--out", str(d)]) == 0
    out = capsys.readouterr().out
    assert "unbounded|sonnet" in out and "template_not_stated|sonnet" not in out  # only the 24 pending unbounded drafts are estimated
    assert mod.main(["judge", "--dry-run", "--drafts", str(d), "--out", str(tmp_path / "j.jsonl")]) == 0
    out = capsys.readouterr().out
    if ns.STANDIN_TEXTS_PATH.is_file():
        assert "Planned 96 judge calls (rubric: 48, template vs unbounded pairwise: 48)" in out and "stand-ins" in out
    else:
        assert "Planned 24 judge calls (rubric: 24, template vs unbounded pairwise: 0)" in out
    assert "Dry run: no API calls made." in out and not (tmp_path / "j.jsonl").exists()
    assert mod.main(["judge", "--drafts", str(d), "--out", str(tmp_path / "j.jsonl")]) == 2  # live judging needs every draft


def test_cli_draft_and_judge_with_fakes_then_resume(tmp_path, replays, capsys):
    mod = _load_script("cat2_not_stated_run")
    d, j = tmp_path / "d.jsonl", tmp_path / "j.jsonl"
    assert mod.main(["draft", "--out", str(d), "--concurrency", "3", "--max-usd", "100"], draft_call=FakeDrafter(replays)) == 0
    assert len(ns.load_jsonl(d)) == 48
    assert mod.main(["draft", "--out", str(d)], draft_call=FakeDrafter(replays)) == 0
    assert "Nothing to do." in capsys.readouterr().out and len(ns.load_jsonl(d)) == 48
    assert mod.main(["judge", "--drafts", str(d), "--out", str(j), "--max-usd", "1000"], judge_call=FakeJudge()) == 0
    recs = ns.load_jsonl(j)
    assert len(recs) == 96 and all(r["meta"] for r in recs)
    assert mod.main(["judge", "--drafts", str(d), "--out", str(j)], judge_call=FakeJudge()) == 0
    assert "Nothing to do." in capsys.readouterr().out


class _Msgs:
    def __init__(self, sink: list, stop: str = "end_turn", text: str = "Long draft.") -> None:
        self.sink, self.stop, self.text = sink, stop, text

    async def create(self, **kw):
        self.sink.append(kw)
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=3000), model=kw["model"])


def test_app_template_call_returns_truncated_draft_when_asked(monkeypatch):
    import anthropic

    from app.core import anthropic_service as svc

    sink: list = []
    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda *a, **k: SimpleNamespace(messages=_Msgs(sink, "max_tokens", '{"executive_summary": {"head')))
    with pytest.raises(RuntimeError, match="max_tokens"):
        asyncio.run(svc.run_cat2_structured_draft("p", "s", {}, "claude-haiku-5-5", "k"))
    raw = asyncio.run(svc.run_cat2_structured_draft("p", "s", {}, "claude-haiku-5-5", "k", raise_on_max_tokens=False))
    assert raw.stop_reason == "max_tokens" and raw.structured == {} and raw.output_tokens == 3000 and raw.raw_text.startswith("{")
    assert raw.request_params["thinking"] == {"type": "disabled"} and raw.request_params["max_tokens"] == 3000


@pytest.mark.parametrize(("tier", "thinking"), [("claude-sonnet-5-5", {"type": "between_tools"}), ("claude-haiku-5-5", {"type": "disabled"})])
def test_app_unbounded_call_uses_the_requested_model(monkeypatch, tier, thinking):
    import anthropic

    from app.core import anthropic_service as svc

    sink: list = []
    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda *a, **k: SimpleNamespace(messages=_Msgs(sink)))
    call = ns.make_app_draft_call("k")
    raw = asyncio.run(call(system="s", payload="p", schema=None, model_tier=tier, max_tokens=8000))
    assert sink[0]["model"].startswith(tier.rsplit("-", 2)[0]) and sink[0]["max_tokens"] == 8000 and sink[0]["thinking"] == thinking
    assert raw.raw_text == "Long draft." and raw.request_params["max_tokens"] == 8000 and raw.stop_reason == "end_turn"
    assert svc.run_cat2_unbounded_sonnet.__kwdefaults__["model_tier"] == "claude-sonnet-5-5"


# --------------------------------------------------------------------------------------------------
# App summary (replays/cat2_quality_summary.json) and golden replays
# --------------------------------------------------------------------------------------------------


def test_app_summary_from_fake_run(replays, jplan):
    drafts = _make_drafts(replays)
    j = _judge_all(jplan)
    s = ns.build_app_summary(drafts, j, source_files={"drafts": "d.jsonl"})
    assert s["schema_version"] == 2 and s["counts"]["drafts"] == 48 and s["counts"]["judge_ok_calls"] == 96
    assert (s["counts"]["rubric_calls"], s["counts"]["pairwise_calls"], s["counts"]["pairwise_planned"]) == (48, 48, 48)
    assert [(c["arm"], c["model_key"], c["status"]) for c in s["cells"]] == [(a, m, "ok") for a in ns.ARMS for m in ns.MODEL_KEYS]
    th = next(c for c in s["cells"] if c["arm"] == ns.ARM_TEMPLATE and c["model_key"] == "haiku")
    uh = next(c for c in s["cells"] if c["arm"] == ns.ARM_UNBOUNDED and c["model_key"] == "haiku")
    assert th["action_items"] == 36 and uh["action_items"] is None and uh["owner"] is None
    assert s["head_to_head"]["status"] == "ok" and s["head_to_head"]["all"]["overall"] == {"template_wins": 48, "unbounded_wins": 0, "ties": 0}
    assert s["head_to_head"]["all"]["position_consistency"] == {"pairs": 24, "consistent": 24}
    rungs = s["presets"]["reg-02"]["rungs"]
    assert set(rungs) == set(ns.APP_RUNG.values())
    h = rungs["haiku_templated"]["head_to_head"][0]
    assert h["opponent"] == "haiku_unbounded" and {o["winner"] for o in h["results"]} == {"haiku_templated"}
    assert {o["shown_first"] for o in h["results"]} == {"haiku_templated", "haiku_unbounded"}
    assert json.dumps(s) == json.dumps(ns.build_app_summary(drafts, j, source_files={"drafts": "d.jsonl"}))


def test_app_summary_with_only_the_template_drafts(replays):
    s = ns.build_app_summary(_template_only(replays), [])
    st = {c["rung_id"]: c["status"] for c in s["cells"]}
    assert st == {"sonnet_unbounded": "pending", "haiku_unbounded": "pending", "sonnet_templated": "ok", "haiku_templated": "ok"}
    assert s["head_to_head"] == {"status": "pending", "all": None, "by_model": {}}
    assert set(s["presets"]["brief-01"]["rungs"]) == {"sonnet_templated", "haiku_templated"}
    assert all(c["rubric"] is None for c in s["cells"])


def test_golden_builder_maps_repeat_zero_and_keeps_section_regens(replays):
    mod = _load_script("build_cat2_golden_from_experiment")
    existing = {"section_regens": {"brief-01": {"x": 1}}}
    g = mod.build_golden(_make_drafts(replays), existing)
    assert g["provenance"]["source"] == mod.GOLDEN_SOURCE and g["provenance"]["pending_rungs"] == []
    assert g["section_regens"] == existing["section_regens"]
    r = g["presets"]["brief-02"]["rungs"]
    assert list(r) == ["sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated"]
    assert r["haiku_unbounded"]["model_id"] == "claude-haiku-5-5" and FILLER in r["haiku_unbounded"]["raw_markdown"]
    assert r["haiku_unbounded"]["structured_draft"]["mode"] == "unbounded_longform_prose" and r["haiku_unbounded"]["max_tokens"] == 8000
    assert "executive_summary" in r["sonnet_templated"]["structured_draft"] and r["sonnet_templated"]["max_tokens"] == 3000
    assert {p["repeat_index"] for p in g["presets"]["brief-02"]["provenance"].values()} == {0}
    g2 = mod.build_golden(_template_only(replays), existing)
    assert g2["provenance"]["pending_rungs"] == ["haiku_unbounded", "sonnet_unbounded"]
    assert list(g2["presets"]["reg-01"]["rungs"]) == ["sonnet_templated", "haiku_templated"]


def test_committed_summary_and_golden_are_current_and_idempotent(tmp_path):
    golden = BACKEND / "replays" / "cat2_golden_replays.json"
    committed = ns.APP_SUMMARY_PATH
    if not (ns.DRAFTS_PATH.is_file() and ns.JUDGEMENTS_PATH.is_file() and committed.is_file() and golden.is_file()):
        pytest.skip("experiment results not present")
    exp_md5 = {p: hashlib.md5(p.read_bytes()).hexdigest() for p in (ns.DRAFTS_PATH, ns.JUDGEMENTS_PATH)}
    mod = _load_script("build_cat2_golden_from_experiment")
    out_g, out_s = tmp_path / "g.json", tmp_path / "s.json"
    out_g.write_text(golden.read_text(encoding="utf-8"), encoding="utf-8")  # the builder keeps the section_regens of the target file
    assert mod.main(["--out", str(out_g), "--summary-out", str(out_s)]) == 0
    assert out_g.read_bytes() == golden.read_bytes() and out_s.read_bytes() == committed.read_bytes()
    assert {p: hashlib.md5(p.read_bytes()).hexdigest() for p in exp_md5} == exp_md5  # read-only
    s = json.loads(out_s.read_text())
    assert {c["rung_id"]: c["drafts"] for c in s["cells"] if c["arm"] == ns.ARM_TEMPLATE} == {"sonnet_templated": 12, "haiku_templated": 12}
    g = json.loads(golden.read_text())
    for pid in qs.PRESET_IDS:
        for rung, v in g["presets"][pid]["rungs"].items():
            cell = s["presets"][pid]["rungs"][rung]
            assert cell["output_tokens"] == v["output_tokens"]  # the replayed draft is the graded draft


# --------------------------------------------------------------------------------------------------
# Record pruning
# --------------------------------------------------------------------------------------------------


def _jl(path: Path, recs: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


def test_prune_keeps_the_two_versions_and_after_rerun_needs_every_record(tmp_path, replays, jplan):
    mod = _load_script("prune_cat2_records")
    exp, first = tmp_path / "exp", tmp_path / "first"
    exp.mkdir()
    first.mkdir()
    drafts = _template_only(replays)
    _jl(exp / "drafts.jsonl", drafts + [{"arm": "template_original", "draft_id": "old", "status": "ok"}])
    rub = [r for r in _judge_all(jplan) if r["meta"]["comparison"] == "rubric" and r["meta"]["arm"] == ns.ARM_TEMPLATE]
    other = [{"call_id": "v", "status": "ok", "meta": {"comparison": "vs_unbounded"}}, {"call_id": "m", "status": "ok", "meta": {"comparison": "matched"}}]
    _jl(exp / "judgements.jsonl", rub + other)
    _jl(first / "judgements.jsonl", [{"task": "rubric", "rung_id": "sonnet_unbounded"}, {"task": "pairwise", "rung_id": None}])
    args = ["--experiment-dir", str(exp), "--first-round-dir", str(first)]
    assert mod.main(args + ["--dry-run"]) == 0 and len(ns.load_jsonl(exp / "drafts.jsonl")) == 25  # dry run writes nothing
    assert mod.main(args) == 0
    assert len(ns.load_jsonl(exp / "drafts.jsonl")) == 24
    assert [(r.get("meta") or {}).get("comparison") for r in ns.load_jsonl(exp / "judgements.jsonl")].count("matched") == 0
    assert len(ns.load_jsonl(exp / "judgements.jsonl")) == len(rub) + 1  # vs_unbounded kept until the rerun
    assert len(ns.load_jsonl(first / "judgements.jsonl")) == 1
    before = (exp / "drafts.jsonl").read_bytes()
    assert mod.main(args) == 0 and (exp / "drafts.jsonl").read_bytes() == before  # idempotent
    assert mod.main(args + ["--after-rerun"]) == 2 and first.is_dir()  # refused: the rerun is not complete
    _jl(exp / "drafts.jsonl", _make_drafts(replays))
    _jl(exp / "judgements.jsonl", _judge_all(jplan) + other)
    assert mod.main(args + ["--after-rerun"]) == 0
    assert not first.exists() and all((r.get("meta") or {}).get("comparison") in ("rubric", ns.COMPARISON) for r in ns.load_jsonl(exp / "judgements.jsonl"))
