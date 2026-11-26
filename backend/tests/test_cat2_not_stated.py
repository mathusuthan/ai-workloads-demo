"""Category 2 "Not stated in source" follow-up: prompts, schema, planning, resume/budget, field classifier,
judge planning, blinding, analysis and the read-only baseline table. No network."""

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
from app.archetypes.cat2_drafting.prompts import get_templated_draft_system_prompt
from app.archetypes.cat2_drafting.schemas import STRUCTURED_DRAFT_JSON_SCHEMA
from app.core.anthropic_service import AnthropicRawResult
from app.data.cat2_fixtures import CAT2_PRESETS

BACKEND = Path(__file__).resolve().parent.parent
PAYLOADS = {p["id"]: p["payload"] for p in CAT2_PRESETS}
SUB_TASKS = sorted({p["sub_task"] for p in CAT2_PRESETS})


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
    """Returns the stored templated draft for the bundle/model; the not_stated arm gets owner/window replaced by the
    literal on reg-02 (the bundle whose source names no owners or dates)."""

    def __init__(self, replays: dict[str, Any], *, truncate_ids=(), fail_ids=()) -> None:
        self.replays = replays
        self.calls: list[dict[str, Any]] = []
        self.truncate = set(truncate_ids)
        self.fail = set(fail_ids)
        self.by_payload = {p["payload"]: p["id"] for p in CAT2_PRESETS}

    async def __call__(self, *, system: str, payload: str, schema: dict[str, Any], model_tier: str, max_tokens: int) -> AnthropicRawResult:
        pid = self.by_payload[payload]
        m = "sonnet" if "sonnet" in model_tier else "haiku"
        arm = ns.ARM_NOT_STATED if ns.ADDED_LINE in system else ns.ARM_ORIGINAL
        n = sum(1 for c in self.calls if (c["pid"], c["m"], c["arm"]) == (pid, m, arm))
        self.calls.append({"pid": pid, "m": m, "arm": arm, "schema": schema, "max_tokens": max_tokens})
        key = ns.draft_key(pid, m, arm, n)
        if key in self.fail:
            raise RuntimeError("overloaded")
        r = self.replays["presets"][pid]["rungs"][ns.STORED_RUNG_FOR_MODEL[m]]
        sd = copy.deepcopy(r["structured_draft"])
        if arm == ns.ARM_NOT_STATED and pid == "reg-02":
            for a in sd["action_plan"]:
                a["owner"], a["target_window"] = "Not stated in source", "Not stated in source"
        raw = json.dumps(sd)
        stop = "end_turn"
        if key in self.truncate:
            raw, sd, stop = raw[: len(raw) // 2], {}, "max_tokens"
        return AnthropicRawResult(model_tier, 900, int(r["input_tokens"]), int(r["output_tokens"]), 0, 0, raw, sd,
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


def _make_drafts(replays, **kw) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    asyncio.run(ns.run_draft_plan(ns.plan_drafts(), draft_call=FakeDrafter(replays, **kw), guard=ns.CostGuard(100),
                                  on_record=recs.append, replays=replays, concurrency=1))
    return recs


# --------------------------------------------------------------------------------------------------
# Prompts and schema
# --------------------------------------------------------------------------------------------------


def test_added_instruction_is_exactly_the_specified_text():
    assert ns.ADDED_INSTRUCTION == (
        "For each action-plan item, give the owner and the time window only if the source states them. "
        "If the source does not name an owner, or gives no date or time window, write exactly `Not stated in source` "
        "in that field. Never supply an owner, team, date or deadline the source does not give."
    )
    assert ns.NOT_STATED == "Not stated in source" and f"`{ns.NOT_STATED}`" in ns.ADDED_INSTRUCTION


@pytest.mark.parametrize("sub_task", SUB_TASKS)
def test_variant_prompt_differs_only_by_the_added_line(sub_task):
    orig, var = ns.original_system_prompt(sub_task), ns.not_stated_system_prompt(sub_task)
    assert orig == get_templated_draft_system_prompt(sub_task)
    diff = ns.prompt_diff(sub_task)
    added = [l for l in diff if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in diff if l.startswith("-") and not l.startswith("---")]
    assert added == ["+" + ns.ADDED_LINE] and removed == []
    assert var.replace(ns.ADDED_LINE, "", 1) == orig and var.count(ns.ADDED_LINE) == 1
    lines = var.splitlines(keepends=True)
    i = lines.index(ns.ADDED_LINE)
    assert lines[i - 1].startswith("- `action_plan`:") and lines[i + 1].startswith("Emit compact JSON")
    assert ns.system_prompt_for(ns.ARM_ORIGINAL, sub_task) == orig and ns.system_prompt_for(ns.ARM_NOT_STATED, sub_task) == var


def test_schema_unchanged_and_shared_by_both_arms():
    snapshot = json.dumps(STRUCTURED_DRAFT_JSON_SCHEMA, sort_keys=True)
    for arm in ns.ARMS:
        assert ns.schema_for(arm) is STRUCTURED_DRAFT_JSON_SCHEMA
    item = STRUCTURED_DRAFT_JSON_SCHEMA["properties"]["action_plan"]["items"]
    assert {"owner", "target_window"} <= set(item["required"])
    assert item["properties"]["owner"] == {"type": "string"} and item["properties"]["target_window"] == {"type": "string"}
    assert len({p["schema_sha256"] for p in ns.plan_drafts()}) == 1
    assert json.dumps(STRUCTURED_DRAFT_JSON_SCHEMA, sort_keys=True) == snapshot
    with pytest.raises(ValueError):
        ns.schema_for("other")


# --------------------------------------------------------------------------------------------------
# Draft planning, estimate, resume, budget guard
# --------------------------------------------------------------------------------------------------


def test_draft_plan_is_48_balanced_and_deterministic():
    plan = ns.plan_drafts()
    assert len(plan) == 48 and len({p["draft_id"] for p in plan}) == 48
    assert [p["draft_id"] for p in plan] == [p["draft_id"] for p in ns.plan_drafts()]
    for field, n in (("arm", 24), ("model_key", 24), ("preset_id", 12), ("repeat_index", 16)):
        assert set(Counter(p[field] for p in plan).values()) == {n}, field
    assert Counter((p["preset_id"], p["model_key"], p["arm"]) for p in plan) == Counter({k: 3 for k in set((p["preset_id"], p["model_key"], p["arm"]) for p in plan)})
    assert {p["repeat_index"] for p in plan[:16]} == {0}  # repeat-major
    assert plan[0]["draft_id"] == "draft:brief-01:sonnet:template_original:r0"
    assert plan[1]["draft_id"] == "draft:brief-01:sonnet:template_not_stated:r0"
    assert {p["model_tier"] for p in plan} == {"claude-sonnet-5-5", "claude-haiku-5-5"}
    assert {p["max_tokens"] for p in plan} == {3000}
    assert all((ns.ADDED_LINE in p["system"]) == (p["arm"] == ns.ARM_NOT_STATED) for p in plan)


def test_draft_estimate_uses_stored_tokens_plus_added_instruction(replays):
    plan = ns.plan_drafts()
    o, v = plan[0], plan[1]
    stored = replays["presets"]["brief-01"]["rungs"]["sonnet_templated"]
    eo, ev = ns.estimate_draft(o, replays), ns.estimate_draft(v, replays)
    assert eo["input_tokens"] == stored["input_tokens"] and ev["input_tokens"] > eo["input_tokens"]
    assert eo["typical_output_tokens"] == stored["output_tokens"]
    assert eo["worst_case_usd"] == pytest.approx((eo["input_tokens"] * 2.0 + 3000 * 10.0) / 1e6)
    tot = ns.estimate_draft_plan(plan, replays)["total"]
    assert tot["drafts"] == 48 and 0 < tot["typical_usd"] < tot["worst_case_usd"] < ns.DEFAULT_DRAFT_MAX_USD


def test_drafting_keeps_truncated_records_errors_and_resumes(replays):
    trunc = ns.draft_key("reg-01", "sonnet", ns.ARM_NOT_STATED, 0)
    fail = ns.draft_key("brief-02", "haiku", ns.ARM_ORIGINAL, 1)
    drafter = FakeDrafter(replays, truncate_ids={trunc}, fail_ids={fail})
    recs: list[dict[str, Any]] = []
    res = asyncio.run(ns.run_draft_plan(ns.plan_drafts(), draft_call=drafter, guard=ns.CostGuard(100), on_record=recs.append,
                                        replays=replays, concurrency=1))
    assert (res["ok"], res["error"], res["truncated"]) == (47, 1, 1)
    assert all(c["max_tokens"] == 3000 and c["schema"] is STRUCTURED_DRAFT_JSON_SCHEMA for c in drafter.calls)
    t = next(r for r in recs if r["draft_key"] == trunc)
    assert t["status"] == "ok" and t["truncated"] is True and t["parse_ok"] is False and t["stop_reason"] == "max_tokens"
    assert t["raw_text"] and t["output_tokens"] > 0  # kept, billed tokens recorded
    e = next(r for r in recs if r["draft_key"] == fail)
    assert e["status"] == "error" and "overloaded" in e["error_message"]
    pending = ns.select_pending_drafts(ns.plan_drafts(), recs)
    assert [p["draft_key"] for p in pending] == [fail]
    assert ns.stale_draft_records(ns.plan_drafts(), recs) == []
    tampered = [{**recs[0], "system_sha256": "x"}]
    assert ns.stale_draft_records(ns.plan_drafts(), tampered) == [recs[0]["draft_id"]]


def test_budget_guard_counts_existing_spend_and_stops_launching(replays):
    plan = ns.plan_drafts()
    worst = ns.estimate_draft(plan[0], replays)["worst_case_usd"]
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


def test_action_items_classified_with_nearest_source_text(replays):
    sd = replays["presets"]["reg-02"]["rungs"]["haiku_templated"]["structured_draft"]
    items = ns.classify_action_items(sd, PAYLOADS["reg-02"])
    assert [i["window_class"] for i in items] == ["unsupported"] * 3  # Within 30 / 45 / 60 days: not in the source
    assert items[0]["owner_class"] == "unsupported" and items[0]["owner_nearest_source"]
    near = items[0]["owner_nearest_source"]
    assert any(near.rstrip("…") in line or line.startswith(near.rstrip("…")) for line in PAYLOADS["reg-02"].splitlines())
    assert ns.classify_action_items({"executive_summary": {}}, PAYLOADS["reg-02"]) == []


# --------------------------------------------------------------------------------------------------
# Judge planning and blinding
# --------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scored(replays, keys):
    return ns.score_drafts(_make_drafts(replays), keys)


@pytest.fixture(scope="module")
def jplan(scored, replays):
    return ns.plan_judge_calls(scored, replays)


def test_judge_plan_counts_orders_and_matching(jplan, replays):
    assert len(jplan) == 112 and len({p["call_id"] for p in jplan}) == 112
    assert Counter(p["meta"]["comparison"] for p in jplan) == {"rubric": 48, "matched": 48, "vs_unbounded": 16}
    rub = [p for p in jplan if p["task"] == "rubric"]
    assert all(p["system"] == qs.RUBRIC_SYSTEM_PROMPT and p["schema"] is qs.RUBRIC_SCHEMA for p in rub)
    pw = [p for p in jplan if p["task"] == "pairwise"]
    assert all(p["system"] == qs.PAIRWISE_SYSTEM_PROMPT and p["schema"] is qs.PAIRWISE_SCHEMA for p in pw)
    units = {}
    for p in pw:
        units.setdefault((p["meta"]["comparison"], p["preset_id"], p["meta"]["model_key"], p["meta"]["draft_repeat"]), []).append(p)
    assert len(units) == 24 + 8
    for (comp, pid, m, k), ps in units.items():
        assert sorted(p["order"] for p in ps) == ["fwd", "rev"]
        fwd, rev = sorted(ps, key=lambda p: p["order"])
        assert fwd["a_rung"] == ns.ARM_NOT_STATED and rev["b_rung"] == ns.ARM_NOT_STATED and fwd["b_rung"] == rev["a_rung"]
        a, b = fwd["meta"]["draft_keys"]
        assert a == ns.draft_key(pid, m, ns.ARM_NOT_STATED, k)
        if comp == "matched":
            assert b == ns.draft_key(pid, m, ns.ARM_ORIGINAL, k)
        else:
            assert k == 0 and b == f"{pid}:{ns.STORED_UNBOUNDED}"
            assert ns.stored_unbounded_text(replays, pid).strip() in fwd["user"]


def test_blinding_holds_over_every_planned_prompt(jplan, scored, replays):
    assert ns.blinding_report(jplan, scored, replays) == {}
    assert any("Not stated in source" in p["user"] for p in jplan)  # inside drafts: allowed
    for p in jplan:
        low = (p["system"] + p["user"]).lower()
        for w in ("template_original", "template_not_stated", "stored_unbounded", "claude-"):
            assert w not in low, (p["call_id"], w)


def test_blinding_catches_planted_leaks(jplan, scored, replays):
    p = next(x for x in jplan if x["task"] == "pairwise")
    for leak in ("\n(arm: template_not_stated)", "\nDraft A came from Haiku.", f"\n{scored[p['meta']['draft_keys'][0]]['output_tokens']} tokens"):
        bad = ns.blinding_report([{**p, "user": p["user"] + leak}], scored, replays)
        assert p["call_id"] in bad, leak


def test_judge_records_carry_baseline_settings(jplan):
    rec = asyncio.run(qs.execute_judge_call(jplan[0], judge_call=FakeJudge()))
    assert rec["status"] == "ok" and rec["judge_model_requested"] == qs.JUDGE_MODEL
    assert rec["settings"] == {"max_tokens": qs.JUDGE_MAX_TOKENS, "thinking": dict(qs.JUDGE_THINKING), "effort": qs.JUDGE_EFFORT,
                               "timeout_s": qs.JUDGE_TIMEOUT_S, "max_retries": 0}


# --------------------------------------------------------------------------------------------------
# Analysis and baseline
# --------------------------------------------------------------------------------------------------


def _judge_all(jplan) -> list[dict[str, Any]]:
    meta = {p["call_id"]: p["meta"] for p in jplan}

    def responder(user, ids):
        if ids is None:
            return pair_obj("B", "A", "B")
        err = {"claim_quote": "Payments Engineering", "problem": "invented owner", "source_quote_or_absent": "ABSENT", "severity": "material"}
        return rubric_obj(ids, scores=(3, 4, 5, 3, 4), errors=[err] if "Payments Engineering" in user else [])

    recs: list[dict[str, Any]] = []

    def on_record(r):
        r["meta"] = meta[r["call_id"]]
        recs.append(r)

    asyncio.run(qs.run_judge_plan(jplan, judge_call=FakeJudge(responder), guard=qs.BudgetGuard(1e6), on_record=on_record, concurrency=8))
    return recs


def test_analysis_without_and_with_judge(replays, jplan):
    drafts = _make_drafts(replays)
    s0 = ns.analyse(drafts, None, baseline_summary=ns.load_baseline_summary())
    assert s0["judge_data_quality"] is None and s0["pairwise"] is None
    g = s0["groups"][f"{ns.ARM_NOT_STATED}|haiku"]["by_preset"]["reg-02"]
    assert g["owner"] == {"supported": 0, "not_stated": 9, "unsupported": 0} and g["time_window"]["not_stated"] == 9
    go = s0["groups"][f"{ns.ARM_ORIGINAL}|haiku"]["by_preset"]["reg-02"]
    assert go["time_window"]["unsupported"] == 9
    assert s0["groups"][f"{ns.ARM_ORIGINAL}|sonnet"]["rubric"] is None
    md0 = ns.render_markdown(s0)
    assert "No judgements file" in md0 and "## Action-item fields (deterministic)" in md0 and "## For lead review" in md0

    recs = _judge_all(jplan)
    s = ns.analyse(drafts, recs, baseline_summary=ns.load_baseline_summary())
    assert s["judge_data_quality"]["ok_calls"] == 112
    gs = s["groups"][f"{ns.ARM_ORIGINAL}|haiku"]
    assert gs["rubric"]["factual_accuracy"]["mean"] == 3 and gs["judged_drafts"] == 12
    assert gs["by_preset"]["reg-02"]["serious_per_draft"]["mean"] == 1  # the planted 'Payments Engineering' error
    assert gs["by_preset"]["reg-02"]["flagged_items_per_draft"]["mean"] == 1  # matched to its action item
    assert s["groups"][f"{ns.ARM_NOT_STATED}|haiku"]["by_preset"]["reg-02"]["serious_per_draft"]["mean"] == 0
    m = s["pairwise"]["matched"]["all"]["overall"]
    # Always 'B': each pair splits 1-1 across the two orders -> every unit position-inconsistent.
    assert (m["not_stated_wins"], m["other_wins"], m["ties"]) == (24, 24, 0)
    assert m["position_consistency"] == {"units_with_both_orders": 24, "consistent": 0}
    assert s["pairwise"]["vs_unbounded"]["all"]["calls"] == 16 and s["pairwise"]["vs_unbounded"]["all"]["overall"]["other"] == ns.STORED_UNBOUNDED
    assert any(e["claim_quote"] == "Payments Engineering" for e in s["review"]["serious_errors"])
    assert any(f["value"] == "Within 30 days" and f["field"] == "time_window" for f in s["review"]["unsupported_fields"])
    md = ns.render_markdown(s)
    for section in ("## Rubric (blind judge", "## Head-to-head", "## Stored baseline, for context", "### Serious errors reported by the judge",
                    "### Owner / time-window fields classified unsupported"):
        assert section in md, section
    json.dumps(s)


def test_baseline_table_reads_summary_without_modifying_it():
    path = ns.BASELINE_SUMMARY_PATH
    before = hashlib.md5(path.read_bytes()).hexdigest()
    bl = ns.baseline_table(ns.load_baseline_summary())
    assert hashlib.md5(path.read_bytes()).hexdigest() == before
    assert [r["serious_errors"] for r in bl["rungs"]] == [1, 6, 10] and bl["drafts_per_cell"] == 1 and bl["passes_per_draft"] == 3
    assert ns.baseline_table(None) is None


def test_analysis_script_with_and_without_judge_file(tmp_path, replays, jplan):
    drafts_path, j_path = tmp_path / "drafts.jsonl", tmp_path / "j.jsonl"
    drafts_path.write_text("".join(json.dumps(r) + "\n" for r in _make_drafts(replays)))
    mod = _load_script("analyze_cat2_not_stated")
    md = tmp_path / "out.md"
    assert mod.main(["--drafts", str(drafts_path), "--judgements", str(tmp_path / "missing.jsonl"), "--out-md", str(md)]) == 0
    assert "No judgements file" in md.read_text() and json.loads(md.with_suffix(".json").read_text())["pairwise"] is None
    j_path.write_text("".join(json.dumps(r) + "\n" for r in _judge_all(jplan)))
    assert mod.main(["--drafts", str(drafts_path), "--judgements", str(j_path), "--out-md", str(md)]) == 0
    assert json.loads(md.with_suffix(".json").read_text())["judge_data_quality"]["ok_calls"] == 112


# --------------------------------------------------------------------------------------------------
# CLI and the app call
# --------------------------------------------------------------------------------------------------


def test_cli_dry_runs_make_no_calls(tmp_path, monkeypatch, capsys):
    import anthropic

    def boom(*a, **k):
        raise AssertionError("dry run must not build a client")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", boom)
    mod = _load_script("cat2_not_stated_run")
    assert mod.main(["draft", "--dry-run", "--out", str(tmp_path / "d.jsonl"), "--show", "2"]) == 0
    out = capsys.readouterr().out
    assert "Planned 48 drafts" in out and "Dry run: no API calls made." in out and not (tmp_path / "d.jsonl").exists()
    assert mod.main(["judge", "--dry-run", "--drafts", str(tmp_path / "d.jsonl"), "--out", str(tmp_path / "j.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "Planned 112 judge calls (rubric: 48, matched pairwise: 48, vs stored unbounded: 16)" in out
    assert "Blinding: 112/112 planned prompts clean." in out and "stand-ins" in out and not (tmp_path / "j.jsonl").exists()
    assert mod.main(["judge", "--drafts", str(tmp_path / "d.jsonl"), "--out", str(tmp_path / "j.jsonl")]) == 2  # live needs drafts


def test_cli_draft_and_judge_with_fakes_then_resume(tmp_path, replays, capsys):
    mod = _load_script("cat2_not_stated_run")
    d, j = tmp_path / "d.jsonl", tmp_path / "j.jsonl"
    assert mod.main(["draft", "--out", str(d), "--concurrency", "3"], draft_call=FakeDrafter(replays)) == 0
    assert len(ns.load_jsonl(d)) == 48
    assert mod.main(["draft", "--out", str(d)], draft_call=FakeDrafter(replays)) == 0
    assert "Nothing to do." in capsys.readouterr().out and len(ns.load_jsonl(d)) == 48
    assert mod.main(["judge", "--drafts", str(d), "--out", str(j)], judge_call=FakeJudge()) == 0
    recs = ns.load_jsonl(j)
    assert len(recs) == 112 and all(r["meta"] and r["experiment"] == "cat2_not_stated" for r in recs)
    assert mod.main(["judge", "--drafts", str(d), "--out", str(j)], judge_call=FakeJudge()) == 0
    assert "Nothing to do." in capsys.readouterr().out


def test_app_call_raise_on_max_tokens_kwarg(monkeypatch):
    import anthropic

    from app.core import anthropic_service as svc

    class _Msgs:
        async def create(self, **kw):
            return SimpleNamespace(stop_reason="max_tokens", content=[SimpleNamespace(type="text", text='{"executive_summary": {"head')],
                                   usage=SimpleNamespace(input_tokens=100, output_tokens=3000), model=kw["model"])

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Msgs()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Client)
    with pytest.raises(RuntimeError, match="max_tokens"):
        asyncio.run(svc.run_cat2_structured_draft("p", "s", {}, "claude-haiku-5-5", "k"))
    raw = asyncio.run(svc.run_cat2_structured_draft("p", "s", {}, "claude-haiku-5-5", "k", raise_on_max_tokens=False))
    assert raw.stop_reason == "max_tokens" and raw.structured == {} and raw.output_tokens == 3000 and raw.raw_text.startswith("{")
    assert raw.request_params["thinking"] == {"type": "disabled"} and raw.request_params["max_tokens"] == 3000


# --------------------------------------------------------------------------------------------------
# App summary (replays/cat2_not_stated_summary.json)
# --------------------------------------------------------------------------------------------------


def test_app_summary_from_fake_run(replays, jplan):
    drafts = _make_drafts(replays)
    s = ns.build_app_summary(drafts, _judge_all(jplan), source_files={"drafts": "d.jsonl"})
    assert s["app_template"] == ns.ARM_ORIGINAL and s["added_instruction"] == ns.ADDED_INSTRUCTION
    assert s["counts"]["drafts"] == 48 and s["counts"]["judge_ok_calls"] == 112
    assert (s["counts"]["rubric_calls"], s["counts"]["pairwise_vs_original_calls"], s["counts"]["pairwise_vs_unbounded_calls"]) == (48, 48, 16)
    assert {(c["arm"], c["model_key"]) for c in s["cells"]} == {(a, m) for a in ns.ARMS for m in ns.MODEL_KEYS}
    hn = next(c for c in s["cells"] if c["arm"] == ns.ARM_NOT_STATED and c["model_key"] == "haiku")
    assert hn["owner_not_stated_by_preset"]["reg-02"] == 9 and hn["action_items"] == 36
    assert s["head_to_head"]["vs_original"]["all"]["overall"] == {"wins": 24, "losses": 24, "ties": 0}
    ex = s["example"]
    assert (ex["preset_id"], ex["model_key"], ex["repeat_index"]) == ("reg-02", "sonnet", 0) and [i["slot"] for i in ex["items"]] == [1, 2, 3]
    assert all(i["not_stated"]["owner"] == "Not stated in source" for i in ex["items"])  # the fake drafter's reg-02 variant
    assert json.dumps(s) == json.dumps(ns.build_app_summary(drafts, _judge_all(jplan), source_files={"drafts": "d.jsonl"}))
    with pytest.raises(ValueError):
        ns.build_app_summary(drafts, [])


def test_committed_app_summary_is_current_and_idempotent(tmp_path):
    committed = BACKEND / "replays" / "cat2_not_stated_summary.json"
    if not (ns.DRAFTS_PATH.is_file() and ns.JUDGEMENTS_PATH.is_file() and committed.is_file()):
        pytest.skip("experiment results not present")
    exp_md5 = {p: hashlib.md5(p.read_bytes()).hexdigest() for p in (ns.DRAFTS_PATH, ns.JUDGEMENTS_PATH)}
    mod = _load_script("build_cat2_not_stated_summary")
    out = tmp_path / "s.json"
    assert mod.main(["--out", str(out)]) == 0
    first = out.read_bytes()
    assert mod.write_if_changed(json.loads(first), out) is False
    assert first == committed.read_bytes()
    assert {p: hashlib.md5(p.read_bytes()).hexdigest() for p in exp_md5} == exp_md5  # read-only
    s = json.loads(first)
    cell = {(c["arm"], c["model_key"]): c for c in s["cells"]}
    assert [round(cell[(a, m)]["serious_per_draft"], 2) for a in ns.ARMS for m in ns.MODEL_KEYS] == [1.25, 2.25, 0.0, 0.25]
    assert cell[(ns.ARM_NOT_STATED, "haiku")]["owner"] == {"supported": 0, "not_stated": 36, "unsupported": 0}
    assert s["head_to_head"]["vs_original"]["all"]["overall"] == {"wins": 47, "losses": 1, "ties": 0}
    assert s["head_to_head"]["vs_unbounded"]["all"]["overall"] == {"wins": 1, "losses": 15, "ties": 0}
