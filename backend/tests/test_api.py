"""Backend test suite for NovaMart AI Workload Archetypes (Phase 0 + Category 1)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.pricing import compute_run_finops  # noqa: E402
from app.data.cat1_fixtures import CAT1_PRESETS  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_traces_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep test runs out of the real backend/traces directory. These tests inspect what a replay request would
    write, so replay traces are switched on here (the app default writes none)."""
    test_traces = tmp_path / "traces"
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(test_traces))
    monkeypatch.setenv("NOVAMART_RECORD_REPLAY_TRACES", "1")
    return test_traces


def test_list_archetypes_returns_all_six_and_finops_rules() -> None:
    resp = client.get("/api/archetypes")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["archetypes"]) == 6
    assert len(body["autonomy_tiers"]) == 4
    assert len(body["token_bands"]) == 5
    assert len(body["finops_rules"]) == 3
    assert body["archetypes"][0]["status"] == "live"
    assert body["archetypes"][1]["status"] == "live"
    assert body["archetypes"][2]["status"] == "live"
    assert body["archetypes"][3]["status"] == "live"
    assert body["archetypes"][4]["status"] == "live"
    assert body["archetypes"][3]["autonomy_tier_label"] == "Tier 2+ (HITL Deep RAG)"
    assert body["archetypes"][4]["autonomy_tier_label"] == "Tier 3+ (Bounded Agentic)"
    assert body["archetypes"][5]["autonomy_tier_label"] == "Tier 4 (Agentic Swarm)"
    assert all(a["status"] == "live" for a in body["archetypes"])


def test_cat1_presets_are_realistic_high_token_payloads() -> None:
    resp = client.get("/api/cat1/presets")
    assert resp.status_code == 200
    presets = resp.json()["presets"]
    assert len(presets) == 6
    assert all(len(p["payload"]) >= 2000 for p in presets)


def test_cat1_run_replay_support_triage_and_pii_masking() -> None:
    resp = client.post(
        "/api/cat1/run",
        json={
            "preset_id": "tkt-02",
            "sub_task": "support_triage",
            "rungs": ["sonnet_naive", "haiku_naive", "sonnet_calibrated", "haiku_calibrated"],
            "mode": "replay",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode_used"] == "replay"
    by_rung = {r["rung_id"]: r for r in data["results"]}

    sonnet = by_rung["sonnet_naive"]
    haiku_naive = by_rung["haiku_naive"]
    haiku = by_rung["haiku_calibrated"]
    sonnet_schema = by_rung["sonnet_calibrated"]

    assert sonnet["finops"]["output_tokens"] > 200
    assert haiku_naive["finops"]["output_tokens"] > 200
    assert haiku_naive["finops"]["cost_per_1k_usd"] < sonnet["finops"]["cost_per_1k_usd"]
    assert haiku["finops"]["cost_per_1k_usd"] < haiku_naive["finops"]["cost_per_1k_usd"]
    assert haiku["finops"]["io_ratio"] >= 12.0
    assert haiku["savings_vs_naive_pct"] > 80.0
    assert sonnet_schema["model_id"] == "claude-sonnet-5-5"
    assert sonnet_schema["finops"]["cost_per_1k_usd"] < sonnet["finops"]["cost_per_1k_usd"]
    assert haiku["finops"]["cost_per_1k_usd"] < sonnet_schema["finops"]["cost_per_1k_usd"]

    # PII scrubbing assertions
    pii = data["pii_redaction"]
    assert pii["contains_pii"] is True
    assert pii["total_redactions"] >= 4
    assert "4829-6173-9042" not in pii["masked_preview"]
    assert "5412-7500-8812-3344" not in pii["masked_preview"]
    assert "[REDACTED_AADHAAR_PII]" in pii["masked_preview"]
    assert "[REDACTED_CARD_PII]" in pii["masked_preview"]

    # Ensure unseparated 12-digit FedEx tracking number on tkt-01 is not misclassified as Aadhaar
    tkt01 = client.post(
        "/api/cat1/run",
        json={
            "preset_id": "tkt-01",
            "sub_task": "support_triage",
            "rungs": ["haiku_calibrated"],
            "mode": "replay",
        },
    ).json()
    assert "AADHAAR" not in tkt01["pii_redaction"]["counts_by_type"]
    assert "774920194812" in tkt01["pii_redaction"]["masked_preview"]


def test_cat1_run_replay_sku_tagging() -> None:
    resp = client.post(
        "/api/cat1/run",
        json={
            "preset_id": "sku-01",
            "sub_task": "sku_tagging",
            "rungs": ["sonnet_naive", "sonnet_calibrated", "haiku_calibrated"],
            "mode": "replay",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    by_rung = {r["rung_id"]: r for r in data["results"]}
    assert by_rung["haiku_calibrated"]["structured_output"]["contradiction_detected"] is True
    assert by_rung["sonnet_calibrated"]["structured_output"]["contradiction_detected"] is True
    assert "jev_comparator" not in data
    assert data["sonnet_batch_comparator"]["cost_per_1k_usd"] < by_rung["sonnet_calibrated"]["finops"]["cost_per_1k_usd"]
    assert data["ground_truth"]["leaf_category"] == "apparel_ethnic_kurtas"
    assert by_rung["sonnet_naive"]["accuracy"]["schema_valid"] is False
    assert by_rung["haiku_calibrated"]["accuracy"]["schema_valid"] is True
    assert by_rung["sonnet_calibrated"]["accuracy"]["exact_match"] is True


def test_cat1_batch_returns_12_items_and_4_cell_cfo_table() -> None:
    resp = client.post("/api/cat1/batch", json={"sub_task": "mixed", "mode": "replay"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 12
    assert len(data["items"]) == 12
    cfo_ids = [r["tier_id"] for r in data["cfo_comparison"]]
    assert cfo_ids == ["sonnet_naive", "haiku_naive", "sonnet_calibrated", "haiku_calibrated"]
    rows = data["cfo_comparison"]
    assert rows[1]["cost_per_1k_usd"] < rows[0]["cost_per_1k_usd"]  # same write-up, smaller model
    assert rows[2]["cost_per_1k_usd"] < rows[0]["cost_per_1k_usd"]  # with vs without on Sonnet
    assert rows[3]["cost_per_1k_usd"] < rows[1]["cost_per_1k_usd"]  # with vs without on Haiku
    assert rows[0]["avg_output_tokens"] != rows[1]["avg_output_tokens"]
    assert rows[0]["avg_input_tokens"] < rows[2]["avg_input_tokens"]  # the schema prompt is longer
    for r in rows:
        assert (r["batch_cost_per_1k_usd"] is not None) == r["tier_id"].endswith("_calibrated")
    assert len(data["accuracy_rollup"]) == 4
    for row in data["accuracy_rollup"]:
        assert 0.0 < row["field_accuracy_pct"] <= 100.0


def test_credit_shield_blocks_missing_keys_cleanly_with_402(
    monkeypatch,
    isolated_traces_dir: Path,
) -> None:
    # Ensure missing keys return clean 402 rather than 500
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app import config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: config.Settings(
            anthropic_api_key="",
            author_passcode="",
            daily_live_budget_usd=2.0,
            anthropic_sonnet_model="claude-sonnet-5-5",
            anthropic_haiku_model="claude-haiku-5-5",
            frontend_dist_dir=Path("/nonexistent"),
            replays_dir=BACKEND_DIR / "replays",
            traces_dir=isolated_traces_dir,
        ),
    )
    from app.core import credit_shield as cs_mod
    monkeypatch.setattr(cs_mod, "get_settings", config.get_settings)

    resp = client.post(
        "/api/cat1/run",
        json={
            "preset_id": "tkt-01",
            "sub_task": "support_triage",
            "rungs": ["sonnet_calibrated", "haiku_calibrated"],
            "mode": "live",
        },
    )
    assert resp.status_code == 402


def test_replay_rejects_modified_custom_input_with_400() -> None:
    resp = client.post(
        "/api/cat1/run",
        json={
            "preset_id": "tkt-01",
            "custom_input": "Some brand new custom payload not in golden replays",
            "sub_task": "support_triage",
            "rungs": ["haiku_calibrated"],
            "mode": "replay",
        },
    )
    assert resp.status_code == 400


def test_pricing_output_multiplier_5x() -> None:
    f = compute_run_finops("claude-sonnet-5-5", input_tokens=1000, output_tokens=1000)
    assert f.input_cost_usd == 0.002
    assert f.output_cost_usd == 0.01
    assert round(f.output_cost_usd / f.input_cost_usd, 1) == 5.0


def test_spa_routes_serve_html_when_built() -> None:
    dist_index = Path(BACKEND_DIR).parent / "frontend" / "dist" / "index.html"
    if not dist_index.is_file():
        return
    for path in ("/", "/archetype/1", "/archetype/2", "/archetype/3", "/archetype/4", "/archetype/5", "/archetype/6"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


def test_trace_capture_partitions_by_category_use_case_model_pattern(
    isolated_traces_dir: Path,
) -> None:
    resp = client.post(
        "/api/cat1/run",
        json={
            "preset_id": "tkt-01",
            "sub_task": "support_triage",
            "rungs": ["sonnet_naive", "haiku_naive", "sonnet_calibrated", "haiku_calibrated"],
            "mode": "replay",
        },
    )
    assert resp.status_code == 200

    expected_dirs = [
        isolated_traces_dir
        / "category=cat1_classification_routing"
        / "use_case=support_triage"
        / "model=claude-sonnet-5-5"
        / "pattern=naive_chatbot",
        isolated_traces_dir
        / "category=cat1_classification_routing"
        / "use_case=support_triage"
        / "model=claude-haiku-5-5"
        / "pattern=naive_unconstrained_prose",
        isolated_traces_dir
        / "category=cat1_classification_routing"
        / "use_case=support_triage"
        / "model=claude-haiku-5-5"
        / "pattern=strict_json_schema",
        isolated_traces_dir
        / "category=cat1_classification_routing"
        / "use_case=support_triage"
        / "model=claude-sonnet-5-5"
        / "pattern=strict_json_schema",
    ]
    for d in expected_dirs:
        files = list(d.glob("*.json"))
        assert len(files) == 1
        trace = json.loads(files[0].read_text(encoding="utf-8"))
        assert trace["request"]["input_payload"]
        assert trace["finops"]["cost_per_1k_usd"] > 0
        raw_str = files[0].read_text(encoding="utf-8")
        assert "sk-ant-" not in raw_str
        assert "AIza" not in raw_str

    summary_resp = client.get("/api/traces/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_traces"] == 4
    assert len(summary["partitions"]) == 4


def test_cat2_presets_match_slide4_input_token_band() -> None:
    resp = client.get("/api/cat2/presets")
    assert resp.status_code == 200
    body = resp.json()
    presets = body["presets"]
    assert len(presets) == 4
    assert all(len(p["payload"]) >= 7000 for p in presets)
    assert "executive_summary" in body["reviewer_presets"]


def test_cat2_run_replay_serves_four_versions_with_output_dominated_cost() -> None:
    for pid, sub_task in (
        ("brief-01", "exec_synthesis"),
        ("brief-02", "exec_synthesis"),
        ("reg-01", "regulatory_filing"),
        ("reg-02", "regulatory_filing"),
    ):
        resp = client.post("/api/cat2/run", json={"preset_id": pid, "sub_task": sub_task, "mode": "replay"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode_used"] == "replay"
        by_rung = {r["rung_id"]: r for r in data["results"]}
        assert list(by_rung) == ["sonnet_unbounded", "haiku_unbounded", "sonnet_templated", "haiku_templated"]
        for m in ("sonnet", "haiku"):
            templated, unbounded = by_rung[f"{m}_templated"], by_rung[f"{m}_unbounded"]
            assert templated["status"] == "ok"
            assert templated["finops"]["output_tokens"] >= 800 and templated["finops"]["output_cost_share_pct"] > 50.0
            assert "executive_summary" in templated["structured_draft"] and len(templated["structured_draft"]["key_findings"]) == 3
            assert unbounded["status"] in ("ok", "pending")
            if unbounded["status"] == "pending":
                assert unbounded["finops"]["total_cost_usd"] == 0 and templated["savings_vs_unbounded_pct"] == 0
            else:
                assert len(unbounded["raw_markdown"] or "") >= 3000 and unbounded["finops"]["output_tokens"] <= 8000
                assert unbounded["finops"]["input_tokens"] < templated["finops"]["input_tokens"]
                assert templated["savings_vs_unbounded_pct"] > 0
        assert by_rung["sonnet_templated"]["finops"]["output_tokens"] != by_rung["haiku_templated"]["finops"]["output_tokens"]


def test_cat2_hitl_section_regeneration_and_partitioned_traces(
    isolated_traces_dir: Path,
) -> None:
    resp = client.post(
        "/api/cat2/regenerate-section",
        json={
            "preset_id": "brief-01",
            "sub_task": "exec_synthesis",
            "section_key": "executive_summary",
            "reviewer_instruction": "",
            "model_tier": "claude-sonnet-5-5",
            "mode": "replay",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["section_key"] == "executive_summary"
    full = body["finops_comparison"]["naive_full_reprompt_finops"]
    golden_full = json.loads((Path(__file__).resolve().parents[1] / "replays" / "cat2_golden_replays.json").read_text(encoding="utf-8"))[
        "presets"]["brief-01"]["rungs"]["sonnet_templated"]
    assert full["model_id"] == "claude-sonnet-5-5"  # compared with the same model's full template draft
    assert (full["input_tokens"], full["output_tokens"]) == (golden_full["input_tokens"], golden_full["output_tokens"])
    assert 0 < body["finops_comparison"]["revision_savings_pct"] < 100
    assert "headline" in body["updated_section"]

    bad_custom = client.post(
        "/api/cat2/regenerate-section",
        json={
            "preset_id": "brief-01",
            "sub_task": "exec_synthesis",
            "section_key": "executive_summary",
            "reviewer_instruction": "Rewrite everything in haiku verse",
            "model_tier": "claude-sonnet-5-5",
            "mode": "replay",
        },
    )
    assert bad_custom.status_code == 400

    regen_dir = (
        isolated_traces_dir
        / "category=cat2_synthesis_drafting"
        / "use_case=exec_synthesis"
        / "model=claude-sonnet-5-5"
        / "pattern=hitl_section_regen"
    )
    trace_files = list(regen_dir.glob("*.json"))
    assert len(trace_files) == 1
    raw_str = trace_files[0].read_text(encoding="utf-8")
    assert "sk-ant-" not in raw_str
    assert "AIza" not in raw_str


def test_cat3_presets_cover_single_it_hr_service_desk_use_case() -> None:
    resp = client.get("/api/cat3/presets")
    assert resp.status_code == 200
    body = resp.json()
    presets = body["presets"]
    assert len(presets) == 2
    assert all(p["use_case"] == "it_hr_service_desk" for p in presets)
    assert all(len(p["turns"]) == 10 for p in presets)
    assert body["handbook_char_count"] >= 11500
    assert "compacted_through_turn" in body["memory_schema"]["properties"]
    assert "prefix_cached_summarized" in body["code_snippets"]


def test_cat3_run_replay_proves_prefix_caching_and_sliding_summary_savings(
    isolated_traces_dir: Path,
) -> None:
    for pid in ("desk-01", "desk-02"):
        resp = client.post("/api/cat3/run", json={"preset_id": pid, "use_case": "it_hr_service_desk", "mode": "replay"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode_used"] == "replay"
        assert body["use_case"] == "it_hr_service_desk"
        by_rung = {r["rung_id"]: r for r in body["results"]}
        assert set(by_rung) == {"naive_full_history", "prefix_cached_summarized"}

        naive = by_rung["naive_full_history"]
        compacted = by_rung["prefix_cached_summarized"]

        for r in (naive, compacted):
            assert r["model_id"] == "claude-sonnet-5-5"
            assert len(r["turns"]) == 10

        # Turns 2..10 must read >= 4,096 cached handbook tokens
        assert compacted["turns"][0]["finops"]["cache_creation_tokens"] + compacted["turns"][0]["finops"]["cache_read_tokens"] >= 4096
        for t in compacted["turns"][1:]:
            assert t["finops"]["cache_read_tokens"] >= 4096
        assert all(t["finops"]["cache_read_tokens"] == 0 for t in naive["turns"])

        assert compacted["summarizer_calls"] == 2
        assert compacted["summarizer_cost_usd"] > 0.0
        assert compacted["turns"][4]["compaction_triggered_before_turn"] is True
        assert compacted["turns"][7]["compaction_triggered_before_turn"] is True

        assert compacted["total_session_cost_usd"] < naive["total_session_cost_usd"]
        assert compacted["warm_fleet_session_cost_usd"] < naive["warm_fleet_session_cost_usd"]

    # an old request naming the removed caching-only version is rejected
    old = client.post("/api/cat3/run", json={"preset_id": "desk-01", "rungs": ["prefix_cached_history"], "mode": "replay"})
    assert old.status_code == 422

    cat3_dir = (
        isolated_traces_dir
        / "category=cat3_conversational_assistants"
        / "use_case=it_hr_service_desk"
        / "model=claude-sonnet-5-5"
        / "pattern=prefix_cached_sliding_summary"
    )
    files = list(cat3_dir.glob("*.json"))
    assert len(files) == 2
    for f in files:
        raw = f.read_text(encoding="utf-8")
        assert "sk-ant-" not in raw
        assert "AIza" not in raw


def test_cat3_chat_turn_rejects_replay_mode_cleanly() -> None:
    resp = client.post(
        "/api/cat3/chat-turn",
        json={
            "preset_id": "desk-01",
            "rung_id": "prefix_cached_summarized",
            "user_message": "What is my Bridge Wire SLA?",
            "mode": "replay",
        },
    )
    assert resp.status_code == 400


# --- Category 4: Multi-Doc RAG & Deep Ingestion Tests ---


def test_no_10k_or_slide_references_in_catalog_and_cat4() -> None:
    arch_resp = client.get("/api/archetypes")
    assert arch_resp.status_code == 200
    arch_json = arch_resp.json()
    arch_blob = json.dumps(arch_json).lower()
    assert "10-k" not in arch_blob
    assert not re.search(r"\bform\s*10\s*-?\s*k\b", arch_blob)
    assert not re.search(r"\bslides?\b", arch_blob)
    cat4_meta_blob = json.dumps(arch_json["archetypes"][3]).lower()
    assert "10-k" not in cat4_meta_blob and "10k" not in cat4_meta_blob

    cat4_resp = client.get("/api/cat4/presets")
    assert cat4_resp.status_code == 200
    cat4_blob = json.dumps(cat4_resp.json()).lower()
    assert "10-k" not in cat4_blob
    assert not re.search(r"\b10k\b", cat4_blob)
    assert not re.search(r"\bslides?\b", cat4_blob)


def test_cat4_presets_expose_7_india_deal_room_docs_and_28_chunks() -> None:
    resp = client.get("/api/cat4/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_docs"] == 7
    assert data["total_chunks"] == 28
    assert len(data["documents"]) == 7
    assert data["corpus_char_count"] >= 38_000
    assert data["approx_corpus_tokens"] >= 15_000
    assert len(data["presets"]) == 2
    for preset in data["presets"]:
        assert preset["use_case"] == "supplier_msa_due_diligence"
        assert len(preset["questions"]) == 4


def test_cat4_run_replay_proves_prefix_cache_and_hybrid_rag_savings_with_citations(
    isolated_traces_dir: Path,
) -> None:
    for pid in ("audit-01", "audit-02"):
        resp = client.post(
            "/api/cat4/run",
            json={"preset_id": pid, "mode": "replay"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode_used"] == "replay"
        assert data["total_docs"] == 7
        assert data["total_chunks"] == 28

        by_rung = {r["rung_id"]: r for r in data["results"]}
        assert set(by_rung) == {"naive_full_corpus", "cached_rerank_hybrid"}
        naive = by_rung["naive_full_corpus"]
        paired = by_rung["cached_rerank_hybrid"]

        assert len(naive["queries"]) == 4
        assert len(paired["queries"]) == 4

        assert naive["avg_citations_per_query"] == 0.0
        assert paired["avg_citations_per_query"] >= 5.0

        assert paired["reranker_calls"] == 4
        assert paired["reranker_cost_usd"] > 0.0
        assert paired["avg_reranker_recall_pct"] >= 90.0
        for i, q in enumerate(paired["queries"]):
            picks = [f for f in q["retrieval_funnel"] if f["stage"] == "selected_by_reranker"]
            assert len(picks) == 5 and [f["pick_rank"] for f in picks] == [1, 2, 3, 4, 5]
            assert q["context_reduction_pct"] >= 65.0
            rf = q["reranker_finops"]
            assert rf["cache_creation_tokens"] + rf["cache_read_tokens"] >= 14_000  # the cached clause block
            if i > 0:
                assert rf["cache_read_tokens"] >= 14_000

        assert paired["single_query_cold_per_1k_usd"] < naive["single_query_cold_per_1k_usd"] * 0.65
        assert paired["cost_per_1k_audits_warm_usd"] < naive["cost_per_1k_audits_warm_usd"] * 0.65

    cat4_dir = (
        isolated_traces_dir
        / "category=cat4_multidoc_rag"
        / "use_case=supplier_msa_due_diligence"
        / "model=claude-sonnet-5-5"
        / "pattern=cached_corpus_haiku_pick_citations"
    )
    files = list(cat4_dir.glob("*.json"))
    assert len(files) == 2
    for f in files:
        raw = f.read_text(encoding="utf-8")
        assert "sk-ant-" not in raw
        assert "AIza" not in raw


def test_cat4_adhoc_query_rejects_replay_mode_cleanly() -> None:
    resp = client.post(
        "/api/cat4/query",
        json={
            "preset_id": "audit-01",
            "question": "When does CPCB EPR certificate EPR-KA-2025-08814 expire?",
            "mode": "replay",
        },
    )
    assert resp.status_code == 400


# --- Category 5: Autonomous Process Orchestration (SQLite ERP Agent) ---


def test_cat5_presets_and_no_slide_or_10k_references() -> None:
    resp = client.get("/api/cat5/presets")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["presets"]) == 3
    assert body["policy_char_count"] >= 14_000
    assert body["approx_policy_tokens"] >= 5_000
    assert "CREATE TABLE reconciliation_vouchers" in body["erp_ddl_schema"]
    blob = json.dumps(body).lower()
    assert "10-k" not in blob
    assert not re.search(r"\b10k\b", blob)
    assert not re.search(r"\bslides?\b", blob)


def test_cat5_sqlite_erp_and_policy_tolerance_gate_determinism() -> None:
    from app.archetypes.cat5_orchestration.erp_db import Cat5ErpSession

    # Ungoverned commit should work on Rung 1, while Governed commit must reject before gate runs
    sess = Cat5ErpSession(rung_id="bounded_sonnet_cached_gate")
    reject_str, _, _, is_opt, _ = sess.execute_tool(
        "commit_reconciliation_voucher",
        {
            "invoice_id": "INV-KA-2026-9921",
            "po_id": "PO-NM-BLR-7740",
            "decision": "APPROVE_CLEAN",
            "authorized_net_principal_inr": 1840000.0,
            "authorized_gst_payout_inr": 331200.0,
            "gst_escrow_holdback_inr": 0.0,
            "debit_note_deduction_inr": 0.0,
            "audit_summary": "unverified",
        },
    )
    assert "REJECTED_BY_GOVERNANCE_GATE" in reject_str
    assert is_opt is False

    # Running gate yields exact ground truth + escalation flags
    for inv_id, exp_dec, exp_esc, exp_halt in (
        ("INV-KA-2026-9921", "APPROVE_WITH_GST_ESCROW", False, False),
        ("INV-MH-2026-4418", "APPROVE_PARTIAL_DEBIT_NOTE", True, False),
        ("INV-DL-2026-8803", "BLOCK_EXCEPTION_HOLD", False, True),
    ):
        _, _, _, _, gate = sess.execute_tool("run_policy_tolerance_gate", {"invoice_id": inv_id})
        assert gate is not None
        assert gate["recommended_decision"] == exp_dec
        assert gate["escalation_required"] is exp_esc
        assert gate["circuit_breaker_halt"] is exp_halt
    sess.close()


def test_cat5_run_replay_reproduces_recorded_runs(
    isolated_traces_dir: Path,
) -> None:
    """Replay must reproduce the recorded runs as they happened (structure, tokens, stop reasons, escalation),
    without asserting what the outcome should have been: the golden runs are ablation repeat 0, not selected."""
    from app.archetypes.cat5_orchestration.runner import load_cat5_replays

    golden = load_cat5_replays()["presets"]
    for pid in ("inv-01", "inv-02", "inv-03"):
        resp = client.post("/api/cat5/run", json={"preset_id": pid, "mode": "replay"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode_used"] == "replay"
        assert len(data["portfolio_scorecard"]) == len(golden[pid]["rungs"]) == 4

        by_rung = {r["rung_id"]: r for r in data["results"]}
        for rid, rec in golden[pid]["rungs"].items():
            res = by_rung[rid]
            assert res["status"] == "ok"
            assert [s["stop_reason"] for s in res["steps"]] == [s["stop_reason"] for s in rec["steps"]]
            assert res["total_uncached_input_tokens"] == sum(s["input_tokens"] for s in rec["steps"])
            assert res["total_cache_read_tokens"] == sum(s["cache_read_tokens"] for s in rec["steps"])
            uncached_rungs = ("unbounded_sonnet_loop", "unbounded_haiku_loop")  # the two "without" rungs: raw tables, no cache
            assert res["steps_used"] <= res["max_step_budget"] + (0 if rid in uncached_rungs else 1)
            assert res["evaluation"] is not None and (res["committed_voucher"] is None) == (rec["committed_voucher"] is None)
            if rid not in uncached_rungs:
                assert res["total_cache_creation_tokens"] + res["total_cache_read_tokens"] > 0  # cached prefix engaged
            else:
                assert res["total_cache_creation_tokens"] + res["total_cache_read_tokens"] == 0

        hybrid = by_rung["hybrid_haiku_sonnet_governed"]
        gate_flagged = any(
            (tc.get("gate_snapshot") or {}).get("escalation_required")
            for st in golden[pid]["rungs"]["hybrid_haiku_sonnet_governed"]["steps"]
            for tc in st["tool_calls"]
        )
        assert hybrid["escalated_to_sonnet"] is gate_flagged  # escalation follows the gate's flag, whatever it was

    cat5_dir = (
        isolated_traces_dir
        / "category=cat5_process_orchestration"
        / "use_case=invoice_3way_reconciliation"
    )
    assert cat5_dir.is_dir()
    trace_files = list(cat5_dir.rglob("*.json"))
    assert len(trace_files) == 12  # 3 invoices x 4 rungs
    for tf in trace_files:
        raw = tf.read_text(encoding="utf-8")
        assert "sk-ant-" not in raw
        assert "AIza" not in raw







# --- Category 6: Multi-Agent Swarms & Auto Eng (Checkout CI Swarm + CpO) ---


def test_cat6_presets_and_no_slide_or_10k_references() -> None:
    resp = client.get("/api/cat6/presets")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["presets"]) == 3
    assert body["shared_repo_char_count"] >= 20_000
    assert body["approx_shared_repo_tokens"] >= 6_000
    assert "ENG-STD-04" in body["shared_repo_preview"]
    assert "SEC-STD-02" in body["shared_repo_preview"]
    assert "CONC-STD-07" in body["shared_repo_preview"]
    blob = json.dumps(body).lower()
    assert "10-k" not in blob
    assert not re.search(r"\b10k\b", blob)
    assert not re.search(r"\bslides?\b", blob)


def test_cat6_python_sandbox_rejects_buggy_and_enforces_ast_security_rules() -> None:
    from app.archetypes.cat6_swarms.sandbox_verifier import evaluate_patch_in_sandbox
    from app.data.cat6_fixtures import CAT6_PRESETS

    for preset in CAT6_PRESETS:
        sbx = evaluate_patch_in_sandbox(preset["id"], preset["buggy_code"])
        assert sbx["total_checks"] == 10
        assert sbx["verified_outcome"] is False
        assert sbx["passed_checks"] < 10

    unsafe_res = evaluate_patch_in_sandbox(
        "inc-02",
        "import subprocess\nclass UpiWebhookProcessor: pass\n",
    )
    assert unsafe_res["verified_outcome"] is False
    safe_chk = next(c for c in unsafe_res["checks"] if c["check_id"] == "AST-SAFE-02")
    assert safe_chk["passed"] is False


def test_cat6_run_replay_proves_context_isolation_prefix_caching_and_cpo(
    isolated_traces_dir: Path,
) -> None:
    for pid in ("inc-01", "inc-02", "inc-03"):
        resp = client.post("/api/cat6/run", json={"preset_id": pid, "mode": "replay"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode_used"] == "replay"
        # 3 rungs while version 2 (shared bus, Haiku agents + Sonnet patch author) is pending, 4 once it is recorded
        recorded_rungs = len(data["results"])
        assert recorded_rungs + len(data["pending_rungs"]) == 4
        assert len(data["portfolio_scorecard"]) == recorded_rungs

        by_rung = {r["rung_id"]: r for r in data["results"]}
        naive = by_rung["unisolated_broadcast_swarm"]
        iso = by_rung["isolated_cached_sonnet_swarm"]
        hybrid = by_rung["tiered_hybrid_cpo_swarm"]

        naive_tot = (
            naive["total_uncached_input_tokens"]
            + naive["total_cache_creation_tokens"]
            + naive["total_cache_read_tokens"]
        )
        assert naive_tot >= 100_000

        for gov in (iso, hybrid):
            sbx = gov["sandbox_report"]
            assert sbx["verified_outcome"] is True
            assert sbx["passed_checks"] == 10
            assert gov["agent_turns"][1]["finops"]["cache_read_tokens"] >= 4096

        assert hybrid["haiku_turns"] >= 4
        assert hybrid["sonnet_turns"] >= 1
        assert hybrid["cold_run_cost_usd"] < iso["cold_run_cost_usd"] < naive["cold_run_cost_usd"]

    cat6_dir = (
        isolated_traces_dir
        / "category=cat6_multi_agent_swarms"
        / "use_case=checkout_ci_self_healing_swarm"
    )
    assert cat6_dir.is_dir()
    trace_files = list(cat6_dir.rglob("*.json"))
    assert len(trace_files) == 3 * recorded_rungs
    for tf in trace_files:
        raw = tf.read_text(encoding="utf-8")
        assert "sk-ant-" not in raw
        assert "AIza" not in raw
