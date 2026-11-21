"""Local Streamlit Trace Explorer for NovaMart AI Workload Archetypes Lab."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.core.trace_store import load_all_traces  # noqa: E402

st.set_page_config(
    page_title="NovaMart AI Trace Explorer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROSE_PATTERNS = (
    "naive_chatbot",
    "naive_unconstrained_prose",
    "unbounded_longform_draft",
    "uncached_full_history",
    "prefix_cached_full_history",
    "prefix_cached_sliding_summary",
    "uncached_full_corpus_stuffing",
    "prefix_cached_full_corpus_citations",
    "hybrid_bm25_haiku_rerank_citations",
    "unbounded_uncached_react_loop",
    "bounded_sonnet_cached_gate",
    "hybrid_haiku_sonnet_governed_loop",
    "unisolated_shared_bus_swarm",
    "isolated_repo_cached_swarm",
    "tiered_hybrid_cpo_swarm",
)
JSON_PATTERNS = (
    "strict_json_schema",
    "section_templated_bounded",
    "tier_routed_template_draft",
    "hitl_section_regen",
    "sliding_window_memory_compactor",
    "haiku_cross_chunk_reranker",
)


def _format_blog_markdown(trace: dict[str, Any]) -> str:
    p = trace.get("partition") or {}
    req = trace.get("request") or {}
    resp = trace.get("response") or {}
    fin = trace.get("finops") or {}

    sys_inst = req.get("system_instruction") or "(None — System-1 closed-set Decision API)"
    output_block = (
        json.dumps(resp.get("decision_probabilities"), indent=2)
        if resp.get("decision_probabilities")
        else (resp.get("raw_text") or json.dumps(resp.get("structured_output"), indent=2))
    )
    return f"""### Trace Snapshot: `{trace.get('item_id')}` · `{p.get('model')}` (`{p.get('pattern')}`)

- **Partition:** `category={p.get('category')}/use_case={p.get('use_case')}/model={p.get('model')}/pattern={p.get('pattern')}`
- **Source Mode:** `{trace.get('source_mode')}` · **Latency:** `{resp.get('latency_ms')} ms`
- **Tokens:** `{fin.get('input_tokens')} uncached in` / `{fin.get('cache_creation_tokens', 0)} cache write` / `{fin.get('cache_read_tokens', 0)} cache read` / `{fin.get('output_tokens')} out` (`I/O: {fin.get('io_ratio_label')}`)
- **Unit Cost:** `${float(fin.get('cost_per_1k_usd', 0.0)):.4f} / 1k runs` (`${float(fin.get('monthly_cost_at_100k_usd', 0.0)):,.2f}/mo @ 100k`)

#### System Instruction
```text
{sys_inst}
```

#### Raw Input Payload ({len(req.get('input_payload', '')):,} chars)
```text
{req.get('input_payload', '')}
```

#### Model Output
```text
{output_block}
```
"""


def _traces_to_dataframe(traces: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for idx, t in enumerate(traces):
        p = t.get("partition") or {}
        fin = t.get("finops") or {}
        resp = t.get("response") or {}
        rows.append(
            {
                "_idx": idx,
                "Timestamp": t.get("timestamp_utc", ""),
                "Item": t.get("item_id", ""),
                "Category": p.get("category", ""),
                "Use Case": p.get("use_case", ""),
                "Model": p.get("model", ""),
                "Pattern": p.get("pattern", ""),
                "Source": t.get("source_mode", ""),
                "In Tok": int(fin.get("input_tokens") or 0),
                "Cache Write": int(fin.get("cache_creation_tokens") or 0),
                "Cache Read": int(fin.get("cache_read_tokens") or 0),
                "Out Tok": int(fin.get("output_tokens") or 0),
                "I/O Ratio": fin.get("io_ratio_label", ""),
                "Latency (ms)": int(resp.get("latency_ms") or 0),
                "Cost / 1k ($)": float(fin.get("cost_per_1k_usd") or 0.0),
                "Status": resp.get("status", "ok"),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    settings = get_settings()
    traces_dir = settings.traces_dir

    st.title("NovaMart AI Trace Explorer")
    st.caption(
        f"Inspect partitioned LLM inputs, system instructions, schemas, outputs & FinOps metrics · Storage: `{traces_dir}`"
    )

    with st.sidebar:
        st.header("Partition Filters")
        if st.button("Refresh Traces from Disk", width="stretch"):
            st.rerun()

    all_traces = load_all_traces(traces_dir)

    with st.sidebar:
        st.metric("Total Captured Traces", len(all_traces))

    if not all_traces:
        st.info(
            "No traces captured yet. Run a request in the web dashboard (`http://127.0.0.1:8000`) "
            "or run `python backend/scripts/seed_traces_from_replays.py`."
        )
        return

    with st.sidebar:
        categories = sorted({(t.get("partition") or {}).get("category", "") for t in all_traces})
        sel_cat = st.selectbox("Category", ["All"] + categories)

        cat_filtered = [
            t
            for t in all_traces
            if sel_cat == "All" or (t.get("partition") or {}).get("category") == sel_cat
        ]
        use_cases = sorted({(t.get("partition") or {}).get("use_case", "") for t in cat_filtered})
        sel_uc = st.selectbox("Use Case", ["All"] + use_cases)

        uc_filtered = [
            t
            for t in cat_filtered
            if sel_uc == "All" or (t.get("partition") or {}).get("use_case") == sel_uc
        ]
        models = sorted({(t.get("partition") or {}).get("model", "") for t in uc_filtered})
        sel_model = st.selectbox("Model", ["All"] + models)

        mod_filtered = [
            t
            for t in uc_filtered
            if sel_model == "All" or (t.get("partition") or {}).get("model") == sel_model
        ]
        patterns = sorted({(t.get("partition") or {}).get("pattern", "") for t in mod_filtered})
        sel_pattern = st.selectbox("Pattern", ["All"] + patterns)

        sources = sorted({str(t.get("source_mode", "")) for t in all_traces})
        sel_source = st.selectbox("Source Mode", ["All"] + sources)

        items = sorted({str(t.get("item_id", "")) for t in all_traces})
        sel_item = st.selectbox("Item / Preset ID", ["All"] + items)

        search_query = st.text_input("Search input/output text", placeholder="e.g. silk, Aadhaar, replacements")

    filtered = []
    q_lower = search_query.strip().lower()
    for t in all_traces:
        p = t.get("partition") or {}
        if sel_cat != "All" and p.get("category") != sel_cat:
            continue
        if sel_uc != "All" and p.get("use_case") != sel_uc:
            continue
        if sel_model != "All" and p.get("model") != sel_model:
            continue
        if sel_pattern != "All" and p.get("pattern") != sel_pattern:
            continue
        if sel_source != "All" and t.get("source_mode") != sel_source:
            continue
        if sel_item != "All" and t.get("item_id") != sel_item:
            continue
        if q_lower:
            haystack = json.dumps(
                {
                    "item": t.get("item_id"),
                    "title": t.get("item_title"),
                    "req": (t.get("request") or {}).get("input_payload"),
                    "resp": (t.get("response") or {}).get("raw_text"),
                    "struct": (t.get("response") or {}).get("structured_output"),
                }
            ).lower()
            if q_lower not in haystack:
                continue
        filtered.append(t)

    tab_inspect, tab_compare, tab_rollup = st.tabs(
        [
            "1. Trace Inspector (Input → Output)",
            "2. Side-by-Side Pattern Comparison",
            "3. Partition Tree & FinOps Rollup",
        ]
    )

    with tab_inspect:
        if not filtered:
            st.warning("No traces match the current sidebar filters.")
        else:
            df = _traces_to_dataframe(filtered)
            st.dataframe(
                df.drop(columns=["_idx"]),
                hide_index=True,
                width="stretch",
                column_config={
                    "Cost / 1k ($)": st.column_config.NumberColumn(format="$%.4f"),
                },
            )

            options = [
                f"{i + 1}. [{t.get('timestamp_utc')}] {t.get('item_id')} · "
                f"{(t.get('partition') or {}).get('model')} · "
                f"{(t.get('partition') or {}).get('pattern')} ({t.get('source_mode')})"
                for i, t in enumerate(filtered)
            ]
            selected_label = st.selectbox("Select Trace to Inspect", options, index=0)
            sel_idx = options.index(selected_label)
            trace = filtered[sel_idx]

            part = trace.get("partition") or {}
            req = trace.get("request") or {}
            resp = trace.get("response") or {}
            fin = trace.get("finops") or {}

            st.markdown("**Partition File Path (relative to `backend/traces/`)**")
            st.code(trace.get("partition_relative_path", ""), language="text")

            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric(
                "Input Tokens",
                f"{int(fin.get('input_tokens') or 0):,}",
                help="Uncached prompt tokens billed at standard rate.",
            )
            cw_tok = int(fin.get("cache_creation_tokens") or 0)
            cr_tok = int(fin.get("cache_read_tokens") or 0)
            k2.metric(
                "Cache W / R",
                f"{cw_tok:,} / {cr_tok:,}" if (cw_tok or cr_tok) else "0 / 0",
                help="Anthropic prefix cache write (1.25x) / cache read (0.1x, -90% discount).",
            )
            k3.metric("Output Tokens", f"{int(fin.get('output_tokens') or 0):,}")
            k4.metric("Latency", f"{int(resp.get('latency_ms') or 0):,} ms")
            k5.metric("Cost / 1k Runs", f"${float(fin.get('cost_per_1k_usd') or 0.0):.4f}")
            k6.metric("Output Cost Share", f"{float(fin.get('output_cost_share_pct') or 0.0):.1f}%")

            col_in, col_out = st.columns(2)

            with col_in:
                st.subheader("Sent to Model (Input Envelope)")
                st.markdown(
                    f"**Provider:** `{req.get('provider')}` · **Endpoint:** `{req.get('endpoint')}` · "
                    f"**Use Case:** `{part.get('use_case')}` · **Pattern:** `{part.get('pattern')}`"
                )
                sys_inst = req.get("system_instruction")
                if sys_inst:
                    st.markdown("**System Instruction**")
                    st.code(sys_inst, language="text")
                else:
                    st.info("No system instruction — Gemini Decisions API evaluates typed questions directly.")

                if req.get("parameters"):
                    with st.expander("Model Request Parameters", expanded=False):
                        st.json(req["parameters"])

                if req.get("json_schema"):
                    with st.expander("Strict JSON Schema Sent (`output_config`)", expanded=False):
                        st.json(req["json_schema"])

                if req.get("decision_questions"):
                    with st.expander("Decision Questions & Rubrics Sent (`questions`)", expanded=False):
                        st.json(req["decision_questions"])

                st.markdown(f"**Raw Input Payload (`{len(req.get('input_payload', '')):,}` chars)**")
                st.text_area(
                    "Input Payload",
                    value=req.get("input_payload", ""),
                    height=340,
                    key=f"in_payload_{trace.get('trace_id')}",
                    label_visibility="collapsed",
                )

            with col_out:
                st.subheader("Returned from Model (Output & Gates)")
                if resp.get("status") == "error":
                    st.error(resp.get("error_message") or "Model execution error")

                if resp.get("raw_text"):
                    render_md = st.toggle(
                        "Render raw output as Markdown",
                        value=part.get("pattern") in PROSE_PATTERNS,
                        key=f"md_toggle_{trace.get('trace_id')}",
                    )
                    if render_md:
                        with st.container(border=True):
                            st.markdown(resp["raw_text"])
                    else:
                        st.code(
                            resp["raw_text"],
                            language="json" if part.get("pattern") in JSON_PATTERNS else "markdown",
                        )

                if resp.get("decision_probabilities"):
                    st.markdown("**Calibrated System-1 Decision Probabilities**")
                    prob_rows = []
                    for q_key, q_val in resp["decision_probabilities"].items():
                        prob_rows.append(
                            {
                                "Question": q_key,
                                "Type": q_val.get("type"),
                                "Selected Value": str(q_val.get("value")),
                                "Confidence": f"{float(q_val.get('confidence', 0.0)) * 100:.1f}%",
                                "Details": json.dumps(
                                    q_val.get("probabilities") or {"p_true": q_val.get("p_true")}
                                ),
                            }
                        )
                    st.dataframe(pd.DataFrame(prob_rows), hide_index=True, width="stretch")

                st.markdown("**Structured Output Parsed**")
                st.json(resp.get("structured_output") or {})

                pii = resp.get("pii_redaction") or {}
                if pii:
                    with st.expander(
                        f"Companion <1ms PII Redaction ({pii.get('total_redactions', 0)} masked)",
                        expanded=False,
                    ):
                        st.write("Counts by type:", pii.get("counts_by_type") or {})
                        st.text_area(
                            "Masked Text Preview",
                            value=pii.get("masked_preview", ""),
                            height=220,
                            key=f"pii_preview_{trace.get('trace_id')}",
                            label_visibility="collapsed",
                        )

                with st.expander("Full FinOps & Trace Metadata", expanded=False):
                    st.json({"finops": fin, "extra_metadata": trace.get("extra_metadata")})

            with st.expander("Blog-Ready Markdown Export & Raw JSON Download", expanded=False):
                blog_md = _format_blog_markdown(trace)
                st.code(blog_md, language="markdown")
                st.download_button(
                    label="Download Trace JSON",
                    data=json.dumps(trace, indent=2),
                    file_name=f"{trace.get('item_id')}_{part.get('model')}_{part.get('pattern')}.json",
                    mime="application/json",
                )

    with tab_compare:
        item_ids = sorted({str(t.get("item_id", "")) for t in all_traces})
        default_idx = item_ids.index("tkt-01") if "tkt-01" in item_ids else 0
        cmp_item = st.selectbox("Select Item ID to Compare Across Models & Patterns", item_ids, index=default_idx)

        item_traces = [t for t in all_traces if t.get("item_id") == cmp_item]
        latest_by_pattern: dict[tuple[str, str], dict[str, Any]] = {}
        for t in item_traces:
            p = t.get("partition") or {}
            key = (str(p.get("model", "")), str(p.get("pattern", "")))
            if key not in latest_by_pattern:
                latest_by_pattern[key] = t

        ordered = sorted(
            latest_by_pattern.values(),
            key=lambda x: float((x.get("finops") or {}).get("cost_per_1k_usd") or 0.0),
            reverse=True,
        )

        if not ordered:
            st.info("No traces found for this item.")
        else:
            cols = st.columns(len(ordered))
            for col, t in zip(cols, ordered):
                p = t.get("partition") or {}
                fin = t.get("finops") or {}
                resp = t.get("response") or {}
                req = t.get("request") or {}
                with col:
                    with st.container(border=True):
                        st.markdown(f"### `{p.get('model')}`")
                        st.caption(f"Pattern: `{p.get('pattern')}` · Source: `{t.get('source_mode')}`")
                        m1, m2 = st.columns(2)
                        m1.metric("Cost / 1k", f"${float(fin.get('cost_per_1k_usd') or 0.0):.4f}")
                        m2.metric("Latency", f"{int(resp.get('latency_ms') or 0)} ms")
                        m3, m4 = st.columns(2)
                        m3.metric("In / Out Tok", f"{fin.get('input_tokens')} / {fin.get('output_tokens')}")
                        cw = int(fin.get("cache_creation_tokens") or 0)
                        cr = int(fin.get("cache_read_tokens") or 0)
                        m4.metric(
                            "Cache W / R" if (cw or cr) else "I/O Ratio",
                            f"{cw:,} / {cr:,}" if (cw or cr) else str(fin.get("io_ratio_label", "—")),
                        )

                        st.markdown("**System / Config**")
                        if req.get("system_instruction"):
                            st.caption(req["system_instruction"])
                        elif req.get("decision_questions"):
                            st.caption(f"{len(req['decision_questions'])} typed Decision API questions (0 out tokens)")

                        st.markdown("**Output**")
                        if resp.get("decision_probabilities"):
                            st.json(resp["structured_output"])
                            with st.expander("Probabilities"):
                                st.json(resp["decision_probabilities"])
                        elif p.get("pattern") in JSON_PATTERNS:
                            st.json(resp.get("structured_output") or {})
                        else:
                            st.text_area(
                                "Prose Output",
                                value=resp.get("raw_text") or "",
                                height=260,
                                key=f"cmp_out_{t.get('trace_id')}",
                                label_visibility="collapsed",
                            )

    with tab_rollup:
        df_all = _traces_to_dataframe(filtered if filtered else all_traces)
        rollup = (
            df_all.groupby(["Category", "Use Case", "Model", "Pattern"], as_index=False)
            .agg(
                Trace_Count=("Item", "count"),
                Avg_In_Tokens=("In Tok", "mean"),
                Avg_Cache_Write=("Cache Write", "mean"),
                Avg_Cache_Read=("Cache Read", "mean"),
                Avg_Out_Tokens=("Out Tok", "mean"),
                Avg_Latency_ms=("Latency (ms)", "mean"),
                Avg_Cost_Per_1k_USD=("Cost / 1k ($)", "mean"),
            )
            .sort_values(["Category", "Use Case", "Avg_Cost_Per_1k_USD"], ascending=[True, True, False])
        )
        rollup["Avg_In_Tokens"] = rollup["Avg_In_Tokens"].round(0).astype(int)
        rollup["Avg_Cache_Write"] = rollup["Avg_Cache_Write"].round(0).astype(int)
        rollup["Avg_Cache_Read"] = rollup["Avg_Cache_Read"].round(0).astype(int)
        rollup["Avg_Out_Tokens"] = rollup["Avg_Out_Tokens"].round(0).astype(int)
        rollup["Avg_Latency_ms"] = rollup["Avg_Latency_ms"].round(0).astype(int)

        st.subheader("Aggregated FinOps Rollup by Partition")
        st.dataframe(
            rollup,
            hide_index=True,
            width="stretch",
            column_config={
                "Avg_Cost_Per_1k_USD": st.column_config.NumberColumn("Avg Cost / 1k ($)", format="$%.4f"),
            },
        )

        st.subheader("Partition Directories on Disk")
        by_dir: dict[str, list[str]] = {}
        for t in (filtered if filtered else all_traces):
            rel = str(t.get("partition_relative_path", ""))
            parent = str(Path(rel).parent) if rel else "unknown"
            by_dir.setdefault(parent, []).append(Path(rel).name)

        for folder, files in sorted(by_dir.items()):
            with st.expander(f"`{folder}` ({len(files)} file{'s' if len(files) != 1 else ''})", expanded=False):
                for fname in sorted(files):
                    st.code(f"{folder}/{fname}", language="text")


if __name__ == "__main__":
    main()
