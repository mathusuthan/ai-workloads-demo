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
    """Keep test runs out of the real backend/traces directory."""
    test_traces = tmp_path / "traces"
    monkeypatch.setenv("NOVAMART_TRACES_DIR", str(test_traces))
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
            "rungs": ["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"],
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
    gemini = by_rung["gemini_decision"]

    assert sonnet["finops"]["output_tokens"] > 200
    assert haiku_naive["finops"]["output_tokens"] > 200
    assert haiku_naive["finops"]["cost_per_1k_usd"] < sonnet["finops"]["cost_per_1k_usd"]
    assert haiku["finops"]["cost_per_1k_usd"] < haiku_naive["finops"]["cost_per_1k_usd"]
    assert haiku["finops"]["io_ratio"] >= 12.0
    assert haiku["savings_vs_naive_pct"] > 80.0
    assert gemini["finops"]["output_tokens"] == 0
    assert gemini["finops"]["output_cost_usd"] == 0.0
    assert gemini["decision_probabilities"]["contains_sensitive_pii"]["type"] == "noul"

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
            "rungs": ["sonnet_naive", "haiku_calibrated", "gemini_decision"],
            "mode": "replay",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    by_rung = {r["rung_id"]: r for r in data["results"]}
    assert by_rung["haiku_calibrated"]["structured_output"]["contradiction_detected"] is True
    assert by_rung["gemini_decision"]["structured_output"]["has_factual_contradiction"] is True
    assert by_rung["gemini_decision"]["finops"]["output_tokens"] == 0
    assert data["jev_comparator"]["input_rate_per_1m_usd"] == 0.042
    assert data["ground_truth"]["leaf_category"] == "apparel_ethnic_kurtas"
    assert by_rung["sonnet_naive"]["accuracy"]["schema_valid"] is False
    assert by_rung["haiku_calibrated"]["accuracy"]["schema_valid"] is True
    assert by_rung["gemini_decision"]["accuracy"]["exact_match"] is True


def test_cat1_batch_returns_12_items_and_5_tier_cfo_table() -> None:
    resp = client.post("/api/cat1/batch", json={"sub_task": "mixed", "mode": "replay"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 12
    assert len(data["items"]) == 12
    cfo_ids = [r["tier_id"] for r in data["cfo_comparison"]]
    assert cfo_ids == [
        "sonnet_naive",
        "haiku_naive",
        "haiku_realtime",
        "haiku_batch",
        "gemini_decision",
        "typesafe_jev",
    ]
    assert data["cfo_comparison"][2]["cost_per_1k_usd"] < data["cfo_comparison"][1]["cost_per_1k_usd"]
    assert data["cfo_comparison"][3]["cost_per_1k_usd"] < data["cfo_comparison"][2]["cost_per_1k_usd"]
    assert data["cfo_comparison"][5]["cost_per_1k_usd"] < data["cfo_comparison"][4]["cost_per_1k_usd"]
    assert data["cfo_comparison"][0]["avg_output_tokens"] != data["cfo_comparison"][1]["avg_output_tokens"]
    assert data["cfo_comparison"][0]["avg_input_tokens"] < data["cfo_comparison"][2]["avg_input_tokens"]
    assert data["cfo_comparison"][4]["avg_input_tokens"] < data["cfo_comparison"][2]["avg_input_tokens"]
    assert data["cfo_comparison"][5]["field_accuracy_pct"] is None
    assert len(data["accuracy_rollup"]) == 4
    for row in data["accuracy_rollup"]:
        assert 0.0 < row["field_accuracy_pct"] <= 100.0


def test_credit_shield_blocks_missing_keys_cleanly_with_402(
    monkeypatch,
    isolated_traces_dir: Path,
) -> None:
    # Ensure missing keys return clean 402 rather than 500
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from app import config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: config.Settings(
            anthropic_api_key="",
            gemini_api_key="",
            author_passcode="",
            daily_live_budget_usd=2.0,
            anthropic_sonnet_model="claude-sonnet-5-5",
            anthropic_haiku_model="claude-haiku-5-5",
            gemini_decision_model="gemini-decision-1",
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
            "rungs": ["haiku_calibrated", "gemini_decision"],
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
            "rungs": ["sonnet_naive", "haiku_naive", "haiku_calibrated", "gemini_decision"],
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
        / "model=gemini-decision-1"
        / "pattern=system1_decisions_api",
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


def test_cat2_run_replay_proves_output_dominated_cost_and_template_savings() -> None:
    distinct_unbounded_out: set[int] = set()
    for pid, sub_task in (
        ("brief-01", "exec_synthesis"),
        ("brief-02", "exec_synthesis"),
        ("reg-01", "regulatory_filing"),
        ("reg-02", "regulatory_filing"),
    ):
        resp = client.post(
            "/api/cat2/run",
            json={
                "preset_id": pid,
                "sub_task": sub_task,
                "rungs": ["sonnet_unbounded", "sonnet_templated", "haiku_templated"],
                "mode": "replay",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode_used"] == "replay"
        by_rung = {r["rung_id"]: r for r in data["results"]}

        unbounded = by_rung["sonnet_unbounded"]
        templated = by_rung["sonnet_templated"]
        haiku = by_rung["haiku_templated"]

        assert len(unbounded["raw_markdown"] or "") >= 3000
        assert unbounded["finops"]["input_tokens"] >= 1500
        assert unbounded["finops"]["output_tokens"] != 4500
        assert unbounded["finops"]["output_tokens"] < 8000
        assert unbounded["finops"]["input_tokens"] < templated["finops"]["input_tokens"]
        assert unbounded["finops"]["output_cost_share_pct"] >= 75.0
        assert templated["finops"]["output_tokens"] >= 800
        assert templated["finops"]["output_tokens"] != haiku["finops"]["output_tokens"]
        assert templated["savings_vs_unbounded_pct"] >= 30.0
        assert haiku["savings_vs_unbounded_pct"] >= 95.0
        assert "executive_summary" in templated["structured_draft"]
        assert len(templated["structured_draft"]["key_findings"]) == 3
        distinct_unbounded_out.add(unbounded["finops"]["output_tokens"])

    assert len(distinct_unbounded_out) >= 3


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
    assert body["finops_comparison"]["revision_savings_pct"] >= 65.0
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
        resp = client.post(
            "/api/cat3/run",
            json={
                "preset_id": pid,
                "use_case": "it_hr_service_desk",
                "rungs": [
                    "naive_full_history",
                    "prefix_cached_history",
                    "prefix_cached_summarized",
                ],
                "mode": "replay",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode_used"] == "replay"
        assert body["use_case"] == "it_hr_service_desk"
        by_rung = {r["rung_id"]: r for r in body["results"]}

        naive = by_rung["naive_full_history"]
        cached = by_rung["prefix_cached_history"]
        compacted = by_rung["prefix_cached_summarized"]

        for r in (naive, cached, compacted):
            assert r["model_id"] == "claude-sonnet-5-5"
            assert len(r["turns"]) == 10

        # Turns 2..10 must read >= 4,096 cached handbook tokens
        for r in (cached, compacted):
            assert r["turns"][0]["finops"]["cache_creation_tokens"] + r["turns"][0]["finops"]["cache_read_tokens"] >= 4096
            for t in r["turns"][1:]:
                assert t["finops"]["cache_read_tokens"] >= 4096

        assert compacted["summarizer_calls"] == 2
        assert compacted["summarizer_cost_usd"] > 0.0
        assert compacted["turns"][4]["compaction_triggered_before_turn"] is True
        assert compacted["turns"][7]["compaction_triggered_before_turn"] is True

        assert compacted["total_session_cost_usd"] < cached["total_session_cost_usd"] < naive["total_session_cost_usd"]
        assert compacted["warm_fleet_session_cost_usd"] < cached["warm_fleet_session_cost_usd"] < naive["warm_fleet_session_cost_usd"]

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
        naive = by_rung["naive_full_corpus"]
        cached = by_rung["cached_full_corpus_citations"]
        hybrid = by_rung["hybrid_rag_rerank_citations"]

        assert len(naive["queries"]) == 4
        assert len(cached["queries"]) == 4
        assert len(hybrid["queries"]) == 4

        assert naive["avg_citations_per_query"] == 0.0
        assert cached["avg_citations_per_query"] >= 5.0
        assert hybrid["avg_citations_per_query"] >= 5.0

        for q in cached["queries"][1:]:
            assert q["finops"]["cache_read_tokens"] >= 14_000

        assert hybrid["reranker_calls"] == 4
        assert hybrid["reranker_cost_usd"] > 0.0
        assert hybrid["avg_reranker_recall_pct"] >= 90.0
        for q in hybrid["queries"]:
            assert len(q["retrieval_funnel"]) == 28
            assert q["context_reduction_pct"] >= 65.0

        assert hybrid["single_query_cold_per_1k_usd"] < naive["single_query_cold_per_1k_usd"] * 0.65
        assert cached["cost_per_1k_audits_warm_usd"] < naive["cost_per_1k_audits_warm_usd"] * 0.50

    cat4_dir = (
        isolated_traces_dir
        / "category=cat4_multidoc_rag"
        / "use_case=supplier_msa_due_diligence"
        / "model=claude-sonnet-5-5"
        / "pattern=hybrid_bm25_haiku_rerank_citations"
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


def test_cat5_run_replay_proves_loop_governance_haiku_routing_and_100pct_accuracy(
    isolated_traces_dir: Path,
) -> None:
    expected_esc = {"inv-01": False, "inv-02": True, "inv-03": False}
    for pid, esc in expected_esc.items():
        resp = client.post("/api/cat5/run", json={"preset_id": pid, "mode": "replay"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode_used"] == "replay"
        assert len(data["portfolio_scorecard"]) == 3

        by_rung = {r["rung_id"]: r for r in data["results"]}
        naive = by_rung["unbounded_sonnet_loop"]
        bounded = by_rung["bounded_sonnet_cached_gate"]
        hybrid = by_rung["hybrid_haiku_sonnet_governed"]

        naive_tot = (
            naive["total_uncached_input_tokens"]
            + naive["total_cache_creation_tokens"]
            + naive["total_cache_read_tokens"]
        )
        assert naive_tot >= 25_000

        for gov in (bounded, hybrid):
            ev = gov["evaluation"]
            assert ev["exact_match"] is True
            assert ev["field_accuracy_pct"] == 100.0
            assert ev["evidence_recall_pct"] == 100.0
            assert ev["tool_precision_pct"] == 100.0
            assert ev["within_step_budget"] is True
            assert ev["gate_verified"] is True
            assert gov["steps"][1]["finops"]["cache_read_tokens"] >= 4096

        assert hybrid["escalated_to_sonnet"] is esc
        assert hybrid["cold_run_cost_usd"] < bounded["cold_run_cost_usd"] < naive["cold_run_cost_usd"]

    cat5_dir = (
        isolated_traces_dir
        / "category=cat5_process_orchestration"
        / "use_case=invoice_3way_reconciliation"
    )
    assert cat5_dir.is_dir()
    trace_files = list(cat5_dir.rglob("*.json"))
    assert len(trace_files) == 9
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
        assert len(data["portfolio_scorecard"]) == 3

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
    assert len(trace_files) == 9
    for tf in trace_files:
        raw = tf.read_text(encoding="utf-8")
        assert "sk-ant-" not in raw
        assert "AIza" not in raw
