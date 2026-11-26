"""Category 1 seven-arm ablation: arms, prompts, call paths (through the app's wrappers with a fake SDK), planning,
resume/superseded/budget, Gemini errors, extraction planning/blinding/parsing, scoring, agreement maths, the
original-capture group and the analysis. No network."""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.archetypes.cat1_triage import ablation as ab
from app.archetypes.cat1_triage.accuracy import extract_prose_predictions
from app.archetypes.cat1_triage.prompts import get_haiku_calibrated_system_prompt, get_sonnet_naive_system_prompt
from app.archetypes.cat1_triage.schemas import get_questions_for_subtask, get_schema_for_subtask
from app.archetypes.cat2_drafting import quality_scoring as qs
from app.core import anthropic_service as svc
from app.core.anthropic_service import AnthropicRawResult
from app.core.gemini_decision_service import GeminiDecisionRawResult

BACKEND = Path(__file__).resolve().parent.parent


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def golden():
    return ab._golden()


# --------------------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------------------


class FakeSDK:
    """Stands in for anthropic.AsyncAnthropic inside app.core.anthropic_service; records every client and call."""

    def __init__(self, text_for=None, stop_reason: str = "end_turn", out_tokens: int = 40, thinking_tokens: int = 0) -> None:
        self.clients: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.text_for = text_for or (lambda kw: '{"ok": true}')
        self.stop_reason, self.out_tokens, self.thinking_tokens = stop_reason, out_tokens, thinking_tokens

    def __call__(self, **kw):
        self.clients.append(kw)
        sdk = self

        class _Messages:
            async def create(self, **call_kw):
                sdk.calls.append(call_kw)
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=sdk.text_for(call_kw))],
                    usage=SimpleNamespace(input_tokens=900, output_tokens=sdk.out_tokens, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                                          output_tokens_details=SimpleNamespace(thinking_tokens=sdk.thinking_tokens)),
                    stop_reason=sdk.stop_reason, model=call_kw["model"],
                )

        return SimpleNamespace(messages=_Messages())


@pytest.fixture
def fake_sdk(monkeypatch):
    sdk = FakeSDK()
    monkeypatch.setattr(svc.anthropic, "AsyncAnthropic", sdk)
    return sdk


def _structured_for(sub_task: str) -> dict[str, Any]:
    props = get_schema_for_subtask(sub_task)["properties"]
    out = {}
    for f, spec in props.items():
        if spec["type"] == "boolean":
            out[f] = True
        elif spec["type"] == "array":
            out[f] = [spec["items"]["enum"][0]]
        else:
            out[f] = spec["enum"][0]
    return out


def _raw(model_id: str, *, text: str = "", structured=None, stop: str = "end_turn", out: int = 50, think: int = 0) -> AnthropicRawResult:
    return AnthropicRawResult(model_id=model_id, latency_ms=100, input_tokens=1000, output_tokens=out, cache_creation_tokens=0, cache_read_tokens=0,
                              raw_text=text, structured=structured if structured is not None else {}, system_prompt="sys",
                              request_params={"max_tokens": 1}, stop_reason=stop, thinking_tokens=think)


class FakeCalls:
    """Injectable CallPaths: prose returns ground-truth `field: value` text; schema returns the ground truth;
    gemini raises unless told otherwise."""

    def __init__(self, *, gemini_ok: bool = False, fail_prose_ids=(), truncate_report: bool = False) -> None:
        self.log: list[tuple[str, dict[str, Any]]] = []
        self.gemini_ok = gemini_ok
        self.fail_prose_ids = set(fail_prose_ids)
        self.truncate_report = truncate_report

    def _item(self, payload: str) -> dict[str, Any]:
        return next(i for i in ab.ITEMS if i["payload"] == payload)

    async def prose(self, **kw):
        self.log.append(("prose", kw))
        item = self._item(kw["payload"])
        if item["id"] in self.fail_prose_ids:
            raise RuntimeError("boom")
        gt = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in item["ground_truth"].items()}
        text = "\n".join(f"{k}: {v}" for k, v in gt.items())
        trunc = self.truncate_report and kw["max_tokens"] == ab.CAPS["report"]
        model = ab.SONNET if kw["model_key"] == "sonnet" else ab.HAIKU
        return _raw(model, text=text, stop="max_tokens" if trunc else "end_turn", out=kw["max_tokens"] if trunc else 30)

    async def schema(self, **kw):
        self.log.append(("schema", kw))
        item = self._item(kw["payload"])
        so = {**_structured_for(item["sub_task"]), **item["ground_truth"]}
        model = ab.SONNET if kw["model_key"] == "sonnet" else ab.HAIKU
        return _raw(model, text=json.dumps(so), structured=so, out=90, think=12 if kw["model_key"] == "sonnet" else 0)

    async def gemini(self, **kw):
        self.log.append(("gemini", kw))
        if not self.gemini_ok:
            raise RuntimeError("GEMINI_API_KEY is not set")
        item = self._item(kw["payload"])
        gt = item["ground_truth"]
        if item["sub_task"] == "support_triage":
            sev = {"P3_LOW": 0, "P2_MEDIUM": 1, "P1_HIGH": 2, "P0_CRITICAL": 3}[gt["priority"]]
            summ = {"queue": gt["queue"], "auto_action": gt["auto_action"], "severity": float(sev), "contains_sensitive_pii": gt["contains_pii"]}
        else:
            summ = {"leaf_category": gt["leaf_category"], "compliance_status": gt["compliance_status"], "hazmat_compliance_risk": 1.0,
                    "has_factual_contradiction": gt["contradiction_detected"]}
        return GeminiDecisionRawResult(model_id=ab.GEMINI, latency_ms=50, input_tokens=max(1, round(len(kw["payload"]) / 3.8)), output_tokens=0,
                                       structured_summary=summ, decision_probabilities={}, request_questions=kw["questions"])

    def paths(self) -> ab.CallPaths:
        return ab.CallPaths(prose=self.prose, schema=self.schema, gemini=self.gemini)


def _run_all(calls: FakeCalls, plan=None, max_usd: float = 100.0) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    asyncio.run(ab.run_plan(plan or ab.plan_runs(), calls=calls.paths(), guard=ab.CostGuard(max_usd), on_record=recs.append, concurrency=8))
    return recs


class FakeJudge:
    """Returns, per field, the value in a `field: value` line of the response (or not_stated), with that line as evidence."""

    def __init__(self, *, override=None, stop: str = "end_turn") -> None:
        self.calls: list[dict[str, Any]] = []
        self.override = override
        self.stop = stop

    async def __call__(self, *, system, user, schema, max_tokens):
        self.calls.append({"system": system, "user": user, "schema": schema, "max_tokens": max_tokens})
        resp = user.split("<response>\n", 1)[1].rsplit("\n</response>", 1)[0]
        fields = {}
        for f, spec in schema["properties"]["fields"]["properties"].items():
            m = re.search(rf"^{f}: (\S+)$", resp, re.M)
            allowed = spec["properties"]["value"]["enum"]
            fields[f] = {"value": m.group(1), "evidence": m.group(0)} if m and m.group(1) in allowed else {"value": "not_stated", "evidence": ""}
        out = {"fields": fields}
        if self.override:
            out = self.override(out)
        return qs.JudgeResponse(model_id=qs.JUDGE_MODEL, stop_reason=self.stop, input_tokens=2000, output_tokens=300, thinking_tokens=100,
                                cache_creation_tokens=0, cache_read_tokens=0, latency_ms=10, raw_text=json.dumps(out))


# --------------------------------------------------------------------------------------------------
# Arms and prompts
# --------------------------------------------------------------------------------------------------


def test_arm_settings():
    assert ab.ARM_IDS == ("sonnet_report", "sonnet_classify_text", "sonnet_schema", "haiku_report", "haiku_classify_text", "haiku_schema", "gemini_decision")
    assert ab.CAPS == {"report": 8192, "classify_text": 1024, "schema": 512}
    assert ab.MAX_RETRIES == 0
    for a in ab.ARMS:
        st = ab.current_settings(a.arm_id, "support_triage")
        if a.model_key == "gemini":
            assert st["model_intended"] == "gemini-decision-1" and "max_tokens" not in st
            continue
        assert st["max_tokens"] == ab.CAPS[a.task]
        assert st["thinking"] == ({"type": "between_tools"} if a.model_key == "sonnet" else {"type": "disabled"})
        assert st["max_retries"] == 0 and st["timeout_s"] > 0
        assert st["model_intended"] == ("claude-sonnet-5-5" if a.model_key == "sonnet" else "claude-haiku-5-5")
        if a.task == "schema":
            assert st["allow_tool_fallback"] is False


@pytest.mark.parametrize("sub_task", ["support_triage", "sku_tagging"])
def test_report_prompts_byte_identical_to_today(sub_task):
    assert ab.system_prompt_for("sonnet_report", sub_task) == get_sonnet_naive_system_prompt(sub_task)
    assert ab.system_prompt_for("haiku_report", sub_task) == get_sonnet_naive_system_prompt(sub_task)
    assert ab.system_prompt_for("haiku_schema", sub_task) == get_haiku_calibrated_system_prompt(sub_task)
    assert ab.system_prompt_for("sonnet_schema", sub_task) == get_haiku_calibrated_system_prompt(sub_task)


@pytest.mark.parametrize("sub_task", ["support_triage", "sku_tagging"])
def test_classify_text_prompt_fields_enums_and_no_ground_truth(sub_task):
    p = ab.classify_text_system_prompt(sub_task)
    schema = get_schema_for_subtask(sub_task)
    assert p.startswith(get_haiku_calibrated_system_prompt(sub_task).split(". ")[0])
    assert p.endswith("Answer with one line per field, `field: value`, using only the allowed values. Do not explain.")
    for f, spec in schema["properties"].items():
        assert re.search(rf"^- {f}: ", p, re.M), f
        for v in (spec.get("enum") or (spec.get("items") or {}).get("enum") or []):
            assert v in p, (f, v)
    assert "true or false" in p
    low = p.lower()
    for word in ("ground truth", "ground_truth", "expected", "schema", "json"):
        assert word not in low
    for item in ab.ITEMS:  # item-independent: no item id, title, or payload text
        assert item["id"] not in p and item["title"] not in p and item["payload"][:60] not in p
    assert ab.classify_text_system_prompt(sub_task) == p
    assert ab.system_prompt_for("sonnet_classify_text", sub_task) == ab.system_prompt_for("haiku_classify_text", sub_task) == p


# --------------------------------------------------------------------------------------------------
# Wrapper overrides: defaults unchanged, overrides reach the SDK (fake)
# --------------------------------------------------------------------------------------------------


def test_wrapper_defaults_unchanged(fake_sdk):
    payload = ab.ITEM_BY_ID["tkt-01"]["payload"]
    asyncio.run(svc.run_sonnet_naive(payload, "support_triage", "k"))
    asyncio.run(svc.run_haiku_naive(payload, "support_triage", "k"))
    asyncio.run(svc.run_haiku_calibrated(payload, "support_triage", get_schema_for_subtask("support_triage"), "k"))
    c_sonnet, c_haiku, c_cal = fake_sdk.calls
    assert fake_sdk.clients == [{"api_key": "k", "timeout": 45.0}, {"api_key": "k", "timeout": 45.0}, {"api_key": "k", "timeout": 30.0}]
    assert c_sonnet["max_tokens"] == 2048 and c_sonnet["thinking"] == {"type": "between_tools"}
    assert c_sonnet["system"] == get_sonnet_naive_system_prompt("support_triage")
    assert c_haiku["max_tokens"] == 2048 and c_haiku["thinking"] == {"type": "disabled"}
    assert c_haiku["system"] == get_sonnet_naive_system_prompt("support_triage")
    assert c_cal["max_tokens"] == 256 and c_cal["thinking"] == {"type": "disabled"} and "claude-haiku" in c_cal["model"]
    assert c_cal["output_config"]["format"]["schema"] == get_schema_for_subtask("support_triage")


def test_calibrated_default_still_falls_back_to_tool_use_on_bad_json(monkeypatch):
    sdk = FakeSDK(text_for=lambda kw: "not json" if "output_config" in kw else "")

    class _Tool(SimpleNamespace):
        pass

    orig = sdk.__call__

    def make(**kw):
        client = orig(**kw)
        create = client.messages.create

        async def create2(**call_kw):
            resp = await create(**call_kw)
            if "tools" in call_kw:
                resp.content = [_Tool(type="tool_use", input={"queue": "replacements"})]
            return resp

        client.messages.create = create2
        return client

    monkeypatch.setattr(svc.anthropic, "AsyncAnthropic", make)
    res = asyncio.run(svc.run_haiku_calibrated("x", "support_triage", get_schema_for_subtask("support_triage"), "k"))
    assert res.structured == {"queue": "replacements"} and res.request_params["tool_choice"]["name"] == "emit_classification"
    assert len(sdk.calls) == 2
    # the ablation's path keeps the unparsed answer instead
    sdk2 = FakeSDK(text_for=lambda kw: '{"queue": "repl', stop_reason="max_tokens")
    monkeypatch.setattr(svc.anthropic, "AsyncAnthropic", sdk2)
    res2 = asyncio.run(svc.run_haiku_calibrated("x", "support_triage", get_schema_for_subtask("support_triage"), "k", allow_tool_fallback=False))
    assert res2.structured == {} and res2.stop_reason == "max_tokens" and len(sdk2.calls) == 1


def test_app_call_paths_send_the_planned_settings(fake_sdk):
    calls = ab.make_app_call_paths("k", None)
    item = ab.ITEM_BY_ID["sku-02"]
    recs = [asyncio.run(ab.execute_run(p, calls=calls)) for p in ab.plan_runs(1, item_ids=["sku-02"])]
    by = {r["arm_id"]: r for r in recs}
    sent = {(c["model"], c["max_tokens"], "output_config" in c): c for c in fake_sdk.calls}
    assert len(fake_sdk.calls) == 6  # gemini never reaches the Anthropic SDK
    assert all(cl.get("max_retries") == 0 for cl in fake_sdk.clients)
    assert sorted(cl["timeout"] for cl in fake_sdk.clients) == sorted([300.0, 120.0, 60.0] * 2)
    s_rep = sent[("claude-sonnet-5-5", 8192, False)]
    h_rep = sent[("claude-haiku-5-5", 8192, False)]
    assert s_rep["system"] == h_rep["system"] == get_sonnet_naive_system_prompt("sku_tagging")
    s_cls = sent[("claude-sonnet-5-5", 1024, False)]
    h_cls = sent[("claude-haiku-5-5", 1024, False)]
    assert s_cls["system"] == h_cls["system"] == ab.classify_text_system_prompt("sku_tagging")
    s_sch = sent[("claude-sonnet-5-5", 512, True)]
    h_sch = sent[("claude-haiku-5-5", 512, True)]
    # Sonnet-schema = Haiku-schema prompt and schema; each model keeps its own thinking
    assert s_sch["system"] == h_sch["system"] == get_haiku_calibrated_system_prompt("sku_tagging")
    assert s_sch["output_config"] == h_sch["output_config"] == {"format": {"type": "json_schema", "schema": get_schema_for_subtask("sku_tagging")}}
    assert s_sch["thinking"] == {"type": "between_tools"} and h_sch["thinking"] == {"type": "disabled"}
    assert s_rep["thinking"] == s_cls["thinking"] == {"type": "between_tools"} and h_rep["thinking"] == h_cls["thinking"] == {"type": "disabled"}
    for c in fake_sdk.calls:
        assert c["messages"] == [{"role": "user", "content": item["payload"]}]
        assert "cache_control" not in json.dumps(c, default=str)
    assert by["gemini_decision"]["status"] == "error" and "GEMINI_API_KEY" in by["gemini_decision"]["error_message"]
    assert all(by[a]["status"] == "ok" and by[a]["model_matches"] for a in ab.ARM_IDS if a != "gemini_decision")


def test_app_gemini_path_calls_the_app_function_unchanged(monkeypatch):
    import app.core.gemini_decision_service as gds

    seen = []

    async def fake(payload_text, questions, api_key):
        seen.append((payload_text, questions, api_key))
        return GeminiDecisionRawResult(model_id="gemini-decision-1", latency_ms=5, input_tokens=400, output_tokens=0,
                                       structured_summary={"queue": "replacements"}, decision_probabilities={"queue": {}})

    monkeypatch.setattr(gds, "run_gemini_decision", fake)
    calls = ab.make_app_call_paths("k", "gk")
    p = next(x for x in ab.plan_runs(1, item_ids=["tkt-01"]) if x["arm_id"] == "gemini_decision")
    rec = asyncio.run(ab.execute_run(p, calls=calls))
    assert seen == [(ab.ITEM_BY_ID["tkt-01"]["payload"], get_questions_for_subtask("support_triage"), "gk")]
    assert rec["status"] == "ok" and rec["decision"]["structured_summary"] == {"queue": "replacements"}
    assert rec["decision"]["input_tokens_possibly_estimated"] is False


# --------------------------------------------------------------------------------------------------
# Planning, resume, superseded, budget
# --------------------------------------------------------------------------------------------------


def test_run_plan_252_balanced_ordered():
    plan = ab.plan_runs()
    assert len(plan) == 252 and len({p["run_id"] for p in plan}) == 252
    assert Counter(p["arm_id"] for p in plan) == {a: 36 for a in ab.ARM_IDS}
    assert Counter(p["item_id"] for p in plan) == {i: 21 for i in ab.ITEM_IDS}
    assert Counter(p["item_group"] for p in plan) == {"preset": 126, "batch": 126}
    keys = [(p["repeat_index"], ab.ITEM_IDS.index(p["item_id"]), ab.ARM_IDS.index(p["arm_id"])) for p in plan]
    assert keys == sorted(keys)
    assert plan[0]["run_id"] == "sonnet_report:tkt-01:r0" and plan[6]["arm_id"] == "gemini_decision"
    assert [p["repeat_index"] for p in plan[:84]] == [0] * 84


def test_full_fake_run_scores_perfectly_and_gemini_errors_are_not_retried_elsewhere():
    calls = FakeCalls(gemini_ok=False)
    recs = _run_all(calls)
    assert len(recs) == 252
    assert Counter(kind for kind, _ in calls.log) == {"prose": 144, "schema": 72, "gemini": 36}
    gem = [r for r in recs if r["arm_id"] == "gemini_decision"]
    assert all(r["status"] == "error" and r["structured_output"] is None and r["raw_text"] is None for r in gem)
    assert all(r["status"] == "ok" for r in recs if r["arm_id"] != "gemini_decision")
    assert all("usd" not in k and "cost" not in k for r in recs for k in r)
    # Gemini errors stay pending; nothing else does
    pending = ab.select_pending(ab.plan_runs(), recs)
    assert {p["arm_id"] for p in pending} == {"gemini_decision"} and len(pending) == 36
    res = ab.analyse(recs, [])
    assert res["data_quality"]["gemini"] == {"records": 36, "ok": 0, "planned": 36}
    assert res["arms"]["haiku_schema"]["accuracy"]["field_accuracy"]["rate"] == 1.0
    assert res["arms"]["sonnet_schema"]["accuracy"]["field_accuracy"]["rate"] == 1.0
    assert res["arms"]["gemini_decision"]["accuracy"] is None
    assert res["arms"]["sonnet_schema"]["thinking_tokens"]["median"] == 12


def test_gemini_ok_path_scored_like_the_app():
    recs = _run_all(FakeCalls(gemini_ok=True), plan=[p for p in ab.plan_runs() if p["arm_id"] == "gemini_decision"])
    assert all(r["status"] == "ok" and r["decision"]["input_tokens_possibly_estimated"] for r in recs)
    res = ab.analyse(recs, [])
    assert res["arms"]["gemini_decision"]["accuracy"]["field_accuracy"] ["rate"] == 1.0
    assert res["arms"]["gemini_decision"]["input_tokens_possibly_estimated"] == 36


def test_truncated_runs_are_flagged_never_dropped():
    recs = _run_all(FakeCalls(truncate_report=True), plan=[p for p in ab.plan_runs() if p["arm_id"].endswith("_report")])
    assert all(r["truncated"] and r["stop_reason"] == "max_tokens" and r["status"] == "ok" for r in recs)
    assert ab.select_pending([p for p in ab.plan_runs() if p["arm_id"].endswith("_report")], recs) == []
    res = ab.analyse(recs, [])
    assert res["arms"]["sonnet_report"]["truncated"] == 36 and res["arms"]["sonnet_report"]["runs"] == 36
    assert res["data_quality"]["truncated"] == 72


def test_errors_retried_resume_and_superseded():
    plan = ab.plan_runs(1, item_ids=["tkt-01", "sku-01"])
    recs = _run_all(FakeCalls(fail_prose_ids={"tkt-01"}, gemini_ok=True), plan=plan)
    failed = {r["run_id"] for r in recs if r["status"] == "error"}
    assert failed == {f"{a}:tkt-01:r0" for a in ab.FREE_TEXT_ARMS}
    assert {p["run_id"] for p in ab.select_pending(plan, recs)} == failed
    # superseded: an ok record made with other settings leaves its run pending and is excluded from analysis
    old = copy.deepcopy(next(r for r in recs if r["run_id"] == "haiku_schema:sku-01:r0"))
    old["settings"] = {**old["settings"], "max_tokens": 256}
    old["settings_sha256"] = ab.settings_sha(old["settings"])
    others = [r for r in recs if r["run_id"] != "haiku_schema:sku-01:r0"]
    mixed = others + [old]
    assert ab.superseded_records(mixed) == [old]
    assert "haiku_schema:sku-01:r0" in {p["run_id"] for p in ab.select_pending(plan, mixed)}
    res = ab.analyse(mixed, [])
    assert res["data_quality"]["superseded_records"] == 1
    assert res["arms"]["haiku_schema"]["runs"] == 1  # only tkt-01


def test_cost_guard_stops_launching_and_counts_recorded_spend(golden):
    plan = ab.plan_runs()
    est0 = ab.estimate_run(plan[0], golden)["worst_case_usd"]
    recs: list[dict[str, Any]] = []
    calls = FakeCalls(gemini_ok=True)
    res = asyncio.run(ab.run_plan(plan, calls=calls.paths(), guard=ab.CostGuard(est0 * 1.01), on_record=recs.append, concurrency=1, golden=golden))
    assert res["budget_stopped"] and res["launched"] >= 1 and res["skipped_budget"] == 252 - res["launched"]
    assert len(recs) == res["launched"]
    g = ab.CostGuard(1.0, recs)
    assert g.spent_usd == pytest.approx(sum(ab.run_cost_usd(r) for r in recs)) and g.spent_usd > 0
    est = ab.estimate_run_plan(plan, golden)
    assert est["total"]["runs"] == 252 and est["total"]["worst_case_usd"] < ab.DEFAULT_RUN_MAX_USD
    assert est["by_arm"]["sonnet_report"]["worst_case_usd"] > est["by_arm"]["haiku_report"]["worst_case_usd"]


# --------------------------------------------------------------------------------------------------
# Extraction: planning, blinding, parsing
# --------------------------------------------------------------------------------------------------


def test_extraction_planning_and_blinding(golden):
    runs = ab.latest_ok_current(_run_all(FakeCalls(gemini_ok=True)))
    plan = ab.plan_extractions(ab.extraction_targets(runs, golden))
    assert Counter(p["source"] for p in plan) == {"run": 144, "golden": 24, "schema_check": 20}
    assert len({p["call_id"] for p in plan}) == len(plan)
    assert ab.blinding_report(plan, runs) == {}
    for p in plan:
        assert p["system"] == ab.EXTRACTION_SYSTEM_PROMPT
        assert "Report what the RESPONSE says" in p["system"]
        fields_block = p["user"].split("<fields>\n", 1)[1].split("\n</fields>", 1)[0]
        assert fields_block == ab.extraction_fields_block(p["sub_task"])
        gt = ab.ITEM_BY_ID[p["item_id"]]["ground_truth"]
        rest = p["user"].replace(ab.ITEM_BY_ID[p["item_id"]]["payload"].strip(), "").replace(p["text"].strip(), "")
        assert "ground" not in rest.lower() and "expected" not in rest.lower()
        assert not any(a in p["system"] + rest for a in ab.ARM_IDS)
    # field block identical across items of a sub-task, and every scalar enum is in it
    for s in ab.SUB_TASKS:
        blocks = {p["user"].split("</fields>")[0] for p in plan if p["sub_task"] == s}
        assert len(blocks) == 1
        block = next(iter(blocks))
        for f in ab.scalar_fields(s):
            for v in (get_schema_for_subtask(s)["properties"][f].get("enum") or ["true", "false"]):
                assert v in block, (s, f, v)
    # forbidden words and token counts are caught
    p0 = dict(plan[0])
    assert ab.extraction_blinding_violations({**p0, "system": p0["system"] + " This response came from Haiku with a 512 token cap."})
    r0 = runs[p0["target_id"]]
    assert ab.extraction_blinding_violations({**p0, "user": p0["user"] + f" ({r0['output_tokens']})"}, [str(r0["output_tokens"])])
    # the judge sees only the response, item, and fields: never settings, arm, model, cost, or tokens
    for p in plan:
        ours = (p["system"] + "\n" + p["user"]).replace(ab.ITEM_BY_ID[p["item_id"]]["payload"].strip(), "").replace(p["text"].strip(), "").lower()
        for leak in ("claude", "sonnet", "haiku", "opus", "gemini", "max_tokens", "thinking", "token", "cost", "$", "schema", "repeat", ":r0", p["source"]):
            assert leak not in ours, (p["call_id"], leak)


def test_extraction_parsing_not_stated_ambiguous_and_invalid():
    p = ab.plan_extractions([{"source": "run", "target_id": "x", "sub_task": "support_triage", "item_id": "tkt-01",
                              "text": "queue: replacements\npriority: P1_HIGH"}])[0]
    rec = asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge()))
    assert rec["status"] == "ok" and rec["evidence_not_verbatim"] == []
    vals = ab.extracted_values(rec["parsed"], "support_triage")
    assert vals["queue"] == "replacements" and vals["priority"] == "P1_HIGH" and vals["contains_pii"] is None and vals["auto_action"] is None

    def amb(o):
        o["fields"]["queue"] = {"value": "ambiguous", "evidence": "replacements or shipping"}
        o["fields"]["contains_pii"] = {"value": "false", "evidence": "no PII"}
        return o

    rec2 = asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge(override=amb)))
    v2 = ab.extracted_values(rec2["parsed"], "support_triage")
    assert rec2["status"] == "ok" and v2["queue"] is None and v2["contains_pii"] is False
    assert rec2["evidence_not_verbatim"] == ["queue", "contains_pii"]  # neither quote is in the response

    def bad_value(o):
        o["fields"]["queue"] = {"value": "returns_desk", "evidence": "x"}
        return o

    rec3 = asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge(override=bad_value)))
    assert rec3["status"] == "error" and rec3["error_type"] == "schema_violation" and rec3["raw_text"]

    def missing(o):
        del o["fields"]["priority"]
        return o

    rec4 = asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge(override=missing)))
    assert rec4["status"] == "error" and rec4["error_type"] == "schema_violation"
    rec5 = asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge(stop="max_tokens")))
    assert rec5["status"] == "error" and rec5["error_type"] == "stop_reason"
    with pytest.raises(ab.ExtractionError):
        ab.parse_extraction("not json", "support_triage")
    # judge settings are the Category 2 judge's
    assert rec["judge_model_requested"] == qs.JUDGE_MODEL and rec["settings"]["max_tokens"] == qs.JUDGE_MAX_TOKENS
    assert rec["settings"]["thinking"] == qs.JUDGE_THINKING and rec["settings"]["effort"] == qs.JUDGE_EFFORT


def test_extraction_schema_allows_only_enums_plus_two_markers():
    s = ab.extraction_schema("sku_tagging")
    f = s["properties"]["fields"]["properties"]
    assert set(f) == {"leaf_category", "hazmat_class", "compliance_status", "contradiction_detected", "primary_material_tag"}
    assert f["contradiction_detected"]["properties"]["value"]["enum"] == ["true", "false", "not_stated", "ambiguous"]
    assert set(ab.ITEM_BY_ID["sku-01"]["ground_truth"]) <= set(f)
    assert set(ab.ITEM_BY_ID["tkt-01"]["ground_truth"]) <= set(ab.extraction_schema("support_triage")["properties"]["fields"]["properties"])


def test_extraction_resume_and_budget():
    plan = ab.plan_extractions([{"source": "run", "target_id": f"t{i}", "sub_task": "sku_tagging", "item_id": "sku-01", "text": "leaf_category: x"}
                                for i in range(5)])
    recs: list[dict[str, Any]] = []
    judge = FakeJudge()
    worst = qs.judge_cost_usd(qs.estimate_input_tokens(plan[0]), qs.JUDGE_MAX_TOKENS)
    res = asyncio.run(ab.run_extraction_plan(plan, judge_call=judge, guard=qs.BudgetGuard(worst + qs.judge_cost_usd(2000, 300) * 1.5), on_record=recs.append, concurrency=1))
    assert res["budget_stopped"] and len(recs) == res["launched"] == 2
    pending = ab.select_pending_extractions(plan, recs)
    assert len(pending) == 5 - len(recs)
    # a changed response text makes the old record stale (pending again)
    plan2 = ab.plan_extractions([{"source": "run", "target_id": "t0", "sub_task": "sku_tagging", "item_id": "sku-01", "text": "leaf_category: y"}])
    assert ab.select_pending_extractions(plan2, recs) == plan2


# --------------------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------------------


def test_scoring_equivalence_schema_path_vs_extracted_path():
    for item in ab.ITEMS:
        sub = item["sub_task"]
        so = {**_structured_for(sub), **item["ground_truth"]}
        if sub == "support_triage":
            so["queue"] = "general_support" if item["ground_truth"]["queue"] != "general_support" else "billing_payouts"
        direct = ab.score_values(item["id"], sub, so)
        text = ab.render_structured_as_text(so, sub)
        p = ab.plan_extractions([{"source": "schema_check", "target_id": item["id"], "sub_task": sub, "item_id": item["id"], "text": text}])[0]
        rec = asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge()))
        via = ab.score_values(item["id"], sub, ab.extracted_values(rec["parsed"], sub))
        assert direct == via
        assert direct["total"] == len(item["ground_truth"])


def test_score_values_uses_the_app_evaluator():
    from app.archetypes.cat1_triage.accuracy import evaluate_rung_accuracy

    item = ab.ITEM_BY_ID["tkt-02"]
    pred = dict(item["ground_truth"], priority="P3_LOW")
    ev = evaluate_rung_accuracy(rung_id="haiku_calibrated", sub_task="support_triage", ground_truth=item["ground_truth"], structured_output=pred, raw_text=None)
    s = ab.score_values("tkt-02", "support_triage", pred)
    assert (s["matched"], s["total"], s["exact"]) == (ev.matched_count, ev.total_fields, ev.exact_match)
    assert s["fields"]["priority"]["matched"] is False
    text = "Queue: replacements. Priority: P1 high."
    r = ab.score_regex("tkt-01", "support_triage", text)
    assert {f: v["actual"] for f, v in r["fields"].items()} == {k: extract_prose_predictions(text, "support_triage").get(k) for k in r["fields"]}


def test_regex_vs_judge_agreement_maths():
    fields = ["a", "b", "c", "d", "e", "f"]
    regex = {"a": "x", "b": "x", "c": None, "d": "x", "e": None, "f": True}
    judge = {"a": "x", "b": "y", "c": "x", "d": None, "e": None, "f": True}
    ag = ab.extractor_agreement(regex, judge, fields)
    assert ag == {"fields": 6, "agree": 3, "same_value": 2, "different_value": 1, "regex_only": 1, "judge_only": 1, "neither": 1}
    assert ab.extractor_agreement({}, {}, []) == {"fields": 0, "agree": 0, "same_value": 0, "different_value": 0, "regex_only": 0, "judge_only": 0, "neither": 0}


def test_schema_check_sample_is_seeded_and_from_schema_arms():
    runs = ab.latest_ok_current(_run_all(FakeCalls(gemini_ok=True)))
    s1 = ab.schema_check_sample(runs)
    s2 = ab.schema_check_sample(dict(reversed(list(runs.items()))))
    assert [r["run_id"] for r in s1] == [r["run_id"] for r in s2] and len(s1) == 20
    assert {r["arm_id"] for r in s1} <= {"sonnet_schema", "haiku_schema"}
    txt = ab.render_structured_as_text(s1[0]["structured_output"], s1[0]["sub_task"])
    assert all(re.match(r"^[a-z_]+: \S", line) for line in txt.splitlines())


# --------------------------------------------------------------------------------------------------
# Original capture group
# --------------------------------------------------------------------------------------------------


def test_golden_capture_group(golden):
    g = ab.golden_prose_responses(golden)
    assert len(g) == 24 and Counter(x["arm_id"] for x in g) == {"sonnet_report": 12, "haiku_report": 12}
    pre = {x["item_id"]: x for x in g if x["arm_id"] == "sonnet_report"}
    assert pre["tkt-01"]["raw_text"] == golden["presets"]["tkt-01"]["rungs"]["sonnet_naive"]["raw_text_preview"]
    assert pre["tkt-04"]["raw_text"] == golden["batch_items"]["tkt-04"]["sonnet_raw_text"]
    hk = {x["item_id"]: x for x in g if x["arm_id"] == "haiku_report"}
    assert hk["sku-04"]["raw_text"] == golden["batch_items"]["sku-04"]["haiku_naive_raw_text"]
    assert sum(x["truncated"] for x in g if x["arm_id"] == "sonnet_report") == 11
    assert sum(x["truncated"] for x in g if x["arm_id"] == "haiku_report") == 8
    res = ab.analyse([], [], golden=golden)
    oc = res["original_capture"]
    assert oc["sonnet_report"]["regex_accuracy"]["field_accuracy"]["total"] == 42 and oc["sonnet_report"]["judge_accuracy"] is None
    assert oc["haiku_schema"]["responses"] == 12 and oc["haiku_schema"]["max_output_tokens_vs_cap"] == {"max": 135, "cap": 256}
    # judged golden responses: regex and judge both reported, with agreement
    plan = [p for p in ab.plan_extractions(ab.extraction_targets({}, golden)) if p["source"] == "golden"]
    ext = [asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge())) for p in plan]
    res2 = ab.analyse([], ext, golden=golden)
    o2 = res2["original_capture"]["haiku_report"]
    assert o2["judged"] == 12 and o2["judge_accuracy"] is not None and o2["extractor_agreement"]["fields"] == 42


# --------------------------------------------------------------------------------------------------
# Analysis and scripts
# --------------------------------------------------------------------------------------------------


def test_analysis_without_records(golden):
    res = ab.analyse([], [], golden=golden)
    assert res["data_quality"]["ok_current_runs"] == 0 and len(res["data_quality"]["missing_runs"]) == 252
    assert all(res["arms"][a]["runs"] == 0 for a in ab.ARM_IDS)
    md = ab.render_markdown(res)
    assert "# Category 1 seven-arm ablation" in md and "## Levers" in md and "## For lead review" in md
    json.dumps(res, default=str)


def test_analysis_with_records_and_judge(golden):
    recs = _run_all(FakeCalls(gemini_ok=True))
    runs = ab.latest_ok_current(recs)
    plan = ab.plan_extractions(ab.extraction_targets(runs, golden))
    ext = [asyncio.run(ab.execute_extraction(p, judge_call=FakeJudge())) for p in plan]
    res = ab.analyse(recs, ext, golden=golden)
    for a in ab.ARM_IDS:
        assert res["arms"][a]["runs"] == 36
        assert res["arms"][a]["accuracy"]["field_accuracy"]["rate"] == 1.0, a
        assert set(res["arms"][a]["by_sub_task"]) == {"support_triage", "sku_tagging"}
    st = res["arms"]["sonnet_classify_text"]
    assert st["judge_value_counts"] == {"stated": 126, "not_stated": 0, "ambiguous": 0}
    assert st["regex_accuracy"] is not None and st["extractor_agreement"]["fields"] == 126
    assert res["schema_check"]["judged"] == 20 and res["schema_check"]["agree"] == res["schema_check"]["fields"] > 0
    assert res["review"]["structured_misses"] == [] and res["data_quality"]["extraction_evidence_not_verbatim"] == []
    lv = {x["lever"]: x for x in res["levers"]}
    assert lv["Sonnet → Haiku (schema)"]["cost_to"] < lv["Sonnet → Haiku (schema)"]["cost_from"]
    assert res["arms"]["haiku_schema"]["batch_cost_per_1k_items_usd_computed"] == pytest.approx(res["arms"]["haiku_schema"]["cost_per_1k_items_usd"] / 2)
    assert res["deck_profile"]["fit"] is not None
    md = ab.render_markdown(res)
    assert "`gemini_decision` | 36 |" in md


def test_scripts_dry_runs_make_no_calls(tmp_path, capsys):
    mod = _load_script("cat1_ablation")

    class Boom:
        def __getattr__(self, k):
            raise AssertionError("no call expected")

    out = tmp_path / "runs.jsonl"
    assert mod.main(["run", "--dry-run", "--out", str(out)], calls=Boom()) == 0
    txt = capsys.readouterr().out
    assert "Planned 252 runs" in txt and "Dry run: no API calls made." in txt and not out.exists()

    async def never(**kw):
        raise AssertionError("no call expected")

    eout = tmp_path / "ext.jsonl"
    assert mod.main(["extract", "--dry-run", "--runs", str(out), "--out", str(eout)], judge_call=never) == 0
    txt = capsys.readouterr().out
    assert "Planned 188 extraction calls" in txt and "188/188 planned prompts clean" in txt and not eout.exists()


def test_scripts_live_path_with_fakes(tmp_path, capsys):
    mod = _load_script("cat1_ablation")
    out = tmp_path / "runs.jsonl"
    calls = FakeCalls(gemini_ok=False)
    assert mod.main(["run", "--out", str(out), "--max-usd", "100", "--concurrency", "6"], calls=calls.paths()) == 0
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert len(lines) == 252 and sum(r["status"] == "error" for r in lines) == 36
    # resume: only the Gemini errors are retried
    calls2 = FakeCalls(gemini_ok=True)
    assert mod.main(["run", "--out", str(out), "--max-usd", "100"], calls=calls2.paths()) == 0
    assert Counter(k for k, _ in calls2.log) == {"gemini": 36}
    eout = tmp_path / "ext.jsonl"
    judge = FakeJudge()
    assert mod.main(["extract", "--runs", str(out), "--out", str(eout), "--max-usd", "1000"], judge_call=judge) == 0
    assert len(judge.calls) == 188
    an = _load_script("analyze_cat1_ablation")
    md, js = tmp_path / "a.md", tmp_path / "a.json"
    assert an.main(["--runs", str(out), "--extractions", str(eout), "--out-md", str(md)]) == 0
    data = json.loads(js.read_text())
    assert data["data_quality"]["gemini"]["ok"] == 36 and data["data_quality"]["extraction_ok_current"] == 188
    assert md.read_text().startswith("# Category 1 seven-arm ablation")
    assert an.main(["--runs", str(tmp_path / "none.jsonl"), "--extractions", str(tmp_path / "none2.jsonl"), "--out-md", str(tmp_path / "e.md")]) == 0
