"""Anthropic Claude API wrappers for Rung 1 (Naive Chat) and Rung 2 (Calibrated Schema)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
import anthropic

from app.archetypes.cat1_triage.prompts import (
    get_haiku_calibrated_system_prompt,
    get_sonnet_naive_system_prompt,
)
from app.config import get_settings


@dataclass
class AnthropicRawResult:
    model_id: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    raw_text: str
    structured: dict[str, Any]
    system_prompt: str = ""
    request_params: dict[str, Any] | None = None
    stop_reason: str | None = None
    thinking_tokens: int = 0


def _extract_usage_tokens(usage: Any) -> tuple[int, int, int, int, int]:
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_create = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    out_details = getattr(usage, "output_tokens_details", None)
    thinking_tokens = int(getattr(out_details, "thinking_tokens", 0) or 0) if out_details else 0
    return input_tokens, output_tokens, cache_create, cache_read, thinking_tokens


async def _create_with_fallback(
    client: anthropic.AsyncAnthropic,
    primary_model: str,
    fallback_models: list[str],
    **kwargs: Any,
) -> tuple[str, Any]:
    candidates = [primary_model] + [m for m in fallback_models if m != primary_model]
    last_exc: Exception | None = None
    for model_id in candidates:
        try:
            resp = await client.messages.create(model=model_id, **kwargs)
            return model_id, resp
        except anthropic.NotFoundError as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    raise RuntimeError("No candidate Anthropic model succeeded.")


async def _run_unconstrained_prose(
    payload_text: str,
    sub_task: str,
    api_key: str,
    primary_model: str,
    fallback_models: list[str],
    *,
    max_tokens: int = 2048,
    system_prompt: str | None = None,
    timeout_s: float = 45.0,
    max_retries: int | None = None,
) -> AnthropicRawResult:
    """Shared single-pass unconstrained prose API helper (no schema; pre-response thinking off).

    Keyword overrides (defaults = the app's behaviour) are used by the Category 1 ablation harness:
    `system_prompt` replaces the naive prompt, `max_retries=None` keeps the SDK default."""
    client = anthropic.AsyncAnthropic(
        api_key=api_key, timeout=timeout_s, **({} if max_retries is None else {"max_retries": max_retries})
    )
    system_prompt = get_sonnet_naive_system_prompt(sub_task) if system_prompt is None else system_prompt
    thinking_cfg: dict[str, str] = (
        {"type": "between_tools"} if "sonnet" in primary_model else {"type": "disabled"}
    )

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        primary_model,
        fallback_models,
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_prompt,
        messages=[{"role": "user", "content": payload_text}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)
    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    raw_text = "\n".join(text_blocks).strip()

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured={"mode": "unstructured_chat_prose", "char_length": len(raw_text)},
        system_prompt=system_prompt,
        request_params={
            "max_tokens": max_tokens,
            "endpoint": "messages.create",
            "thinking": thinking_cfg,
        },
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


async def run_sonnet_naive(
    payload_text: str,
    sub_task: str,
    api_key: str,
    redact_hint_text: str | None = None,
    **prose_overrides: Any,
) -> AnthropicRawResult:
    """Rung 1A Anti-Pattern: Verbose Unconstrained Prose Prompt on Sonnet 5.5.

    `prose_overrides`: optional keyword overrides of `_run_unconstrained_prose` (max_tokens, system_prompt,
    timeout_s, max_retries); none are passed by the app."""
    settings = get_settings()
    return await _run_unconstrained_prose(
        payload_text=payload_text,
        sub_task=sub_task,
        api_key=api_key,
        primary_model=settings.anthropic_sonnet_model,
        fallback_models=["claude-sonnet-5-5", "claude-sonnet-4-6"],
        **prose_overrides,
    )


async def run_haiku_naive(
    payload_text: str,
    sub_task: str,
    api_key: str,
    **prose_overrides: Any,
) -> AnthropicRawResult:
    """Rung 1B Ablation: Same Unconstrained Prose Single-Pass API Call on Haiku 5.5 (overrides as run_sonnet_naive)."""
    settings = get_settings()
    return await _run_unconstrained_prose(
        payload_text=payload_text,
        sub_task=sub_task,
        api_key=api_key,
        primary_model=settings.anthropic_haiku_model,
        fallback_models=["claude-haiku-5-5", "claude-haiku-4-5"],
        **prose_overrides,
    )


async def run_haiku_calibrated(
    payload_text: str,
    sub_task: str,
    schema: dict[str, Any],
    api_key: str,
    *,
    model: str | None = None,
    fallback_models: list[str] | None = None,
    max_tokens: int = 256,
    thinking: dict[str, str] | None = None,
    timeout_s: float = 30.0,
    max_retries: int | None = None,
    allow_tool_fallback: bool = True,
) -> AnthropicRawResult:
    """Rung 2: Haiku 5.5 asked for the classification fields only, through a JSON schema (compact output).

    Keyword overrides (defaults = the app's behaviour) are used by the Category 1 ablation harness: `model`
    (+ `fallback_models`) runs the same prompt and schema on another model, `thinking` sets that model's thinking,
    `allow_tool_fallback=False` keeps an unparsable/truncated JSON answer (structured={}) instead of silently
    re-asking via tool use, and re-raises an API rejection instead of switching call path."""
    settings = get_settings()
    client = anthropic.AsyncAnthropic(
        api_key=api_key, timeout=timeout_s, **({} if max_retries is None else {"max_retries": max_retries})
    )
    system_prompt = get_haiku_calibrated_system_prompt(sub_task)
    primary = model or settings.anthropic_haiku_model
    fallbacks = fallback_models if fallback_models is not None else ["claude-haiku-5-5", "claude-haiku-4-5"]
    thinking_cfg = thinking or {"type": "disabled"}

    t0 = time.perf_counter()
    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "thinking": thinking_cfg,
        "output_config": {"format": {"type": "json_schema"}},
    }
    try:
        used_model, resp = await _create_with_fallback(
            client,
            primary,
            fallbacks,
            max_tokens=max_tokens,
            thinking=thinking_cfg,
            system=system_prompt,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": schema,
                }
            },
            messages=[{"role": "user", "content": payload_text}],
        )
        raw_text = "\n".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        try:
            structured = json.loads(raw_text) if raw_text else {}
        except json.JSONDecodeError:
            if allow_tool_fallback:
                raise
            structured = {}
    except (anthropic.BadRequestError, TypeError, json.JSONDecodeError):
        if not allow_tool_fallback:
            raise
        request_params = {
            "max_tokens": 256,
            "thinking": {"type": "disabled"},
            "tool_choice": {"type": "tool", "name": "emit_classification"},
        }
        # Fallback to strict tool-use if a snapshot rejects output_config
        used_model, resp = await _create_with_fallback(
            client,
            settings.anthropic_haiku_model,
            ["claude-haiku-5-5", "claude-haiku-4-5"],
            max_tokens=256,
            thinking={"type": "disabled"},
            system=system_prompt,
            tools=[
                {
                    "name": "emit_classification",
                    "description": "Emit strict Tier-1 classification object.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "emit_classification"},
            messages=[{"role": "user", "content": payload_text}],
        )
        structured = {}
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                structured = dict(block.input)
                break
        raw_text = json.dumps(structured)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured=structured,
        system_prompt=system_prompt,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


async def run_cat2_unbounded_sonnet(
    payload_text: str,
    system_prompt: str,
    api_key: str,
    max_tokens: int = 8000,
    *,
    model_tier: str = "claude-sonnet-5-5",
) -> AnthropicRawResult:
    """Category 2 without the lever: unbounded long-form draft (free text).

    `model_tier` selects Sonnet 5.5 (default; thinking between tools) or Haiku 5.5 (thinking disabled), the same
    per-model settings as the templated call."""
    settings = get_settings()
    is_sonnet = "sonnet" in model_tier
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0)
    thinking_cfg: dict[str, str] = {"type": "between_tools"} if is_sonnet else {"type": "disabled"}

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        settings.anthropic_sonnet_model if is_sonnet else settings.anthropic_haiku_model,
        ["claude-sonnet-5-5", "claude-sonnet-4-6"] if is_sonnet else ["claude-haiku-5-5", "claude-haiku-4-5"],
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_prompt,
        messages=[{"role": "user", "content": payload_text}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)
    raw_text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured={"mode": "unbounded_longform_prose", "char_length": len(raw_text)},
        system_prompt=system_prompt,
        request_params={
            "max_tokens": max_tokens,
            "endpoint": "messages.create",
            "thinking": thinking_cfg,
        },
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


async def run_cat2_structured_draft(
    payload_text: str,
    system_prompt: str,
    schema: dict[str, Any],
    model_tier: str,
    api_key: str,
    max_tokens: int = 3000,
    *,
    raise_on_max_tokens: bool = True,
) -> AnthropicRawResult:
    """Category 2 Templated / Surgical Section synthesis via strict JSON schema (thinking disabled on Haiku only).

    raise_on_max_tokens=False (experiments only) returns a truncated draft instead of raising: its text, usage and
    stop_reason are kept, and `structured` is {} when the JSON does not parse.
    """
    settings = get_settings()
    is_sonnet = "sonnet" in model_tier
    primary_model = settings.anthropic_sonnet_model if is_sonnet else settings.anthropic_haiku_model
    fallback_models = (
        ["claude-sonnet-5-5", "claude-sonnet-4-6"]
        if is_sonnet
        else ["claude-haiku-5-5", "claude-haiku-4-5"]
    )
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=60.0)
    thinking_cfg: dict[str, str] = (
        {"type": "between_tools"} if is_sonnet else {"type": "disabled"}
    )

    t0 = time.perf_counter()
    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "thinking": thinking_cfg,
        "output_config": {"format": {"type": "json_schema"}},
    }
    used_model, resp = await _create_with_fallback(
        client,
        primary_model,
        fallback_models,
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_prompt,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": schema,
            }
        },
        messages=[{"role": "user", "content": payload_text}],
    )
    raw_text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    if getattr(resp, "stop_reason", None) == "max_tokens" and raise_on_max_tokens:
        out_cnt = int(getattr(resp.usage, "output_tokens", 0) or 0)
        raise RuntimeError(
            f"Structured draft hit max_tokens={max_tokens} ({out_cnt} out tokens)"
        )
    if raise_on_max_tokens:
        structured = json.loads(raw_text) if raw_text else {}
    else:
        try:
            structured = json.loads(raw_text) if raw_text else {}
        except json.JSONDecodeError:
            structured = {}

    latency_ms = int((time.perf_counter() - t0) * 1000)
    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured=structured,
        system_prompt=system_prompt,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


async def run_cat3_service_desk_turn(
    system_text: str,
    messages: list[dict[str, Any]],
    use_prefix_cache: bool,
    api_key: str,
    max_tokens: int = 4096,
    timeout_s: float = 60.0,
) -> AnthropicRawResult:
    """Category 3 multi-turn IT & HR Service Desk call on Sonnet 5.5 with optional prefix cache_control."""
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)
    thinking_cfg: dict[str, str] = {"type": "between_tools"}

    system_arg: Any = (
        [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if use_prefix_cache
        else system_text
    )
    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "endpoint": "messages.create",
        "thinking": thinking_cfg,
        "prefix_cache_enabled": use_prefix_cache,
        "turn_messages_count": len(messages),
    }

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        settings.anthropic_sonnet_model,
        ["claude-sonnet-5-5", "claude-sonnet-4-6"],
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_arg,
        messages=messages,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    raw_text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured={"mode": "service_desk_turn", "turn_messages": len(messages)},
        system_prompt=system_text,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


async def run_cat3_memory_summarizer(
    compaction_payload: str,
    system_prompt: str,
    schema: dict[str, Any],
    api_key: str,
    max_tokens: int = 1600,
    timeout_s: float = 60.0,
) -> AnthropicRawResult:
    """Category 3 sliding-window session state compressor on Sonnet 5.5 via strict JSON schema."""
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)
    thinking_cfg: dict[str, str] = {"type": "between_tools"}
    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "endpoint": "messages.create",
        "thinking": thinking_cfg,
        "output_config": {"format": {"type": "json_schema"}},
    }

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        settings.anthropic_sonnet_model,
        ["claude-sonnet-5-5", "claude-sonnet-4-6"],
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_prompt,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": schema,
            }
        },
        messages=[{"role": "user", "content": compaction_payload}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    raw_text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    if getattr(resp, "stop_reason", None) == "max_tokens":
        out_cnt = int(getattr(resp.usage, "output_tokens", 0) or 0)
        raise RuntimeError(
            f"Category 3 memory summarizer hit max_tokens={max_tokens} ({out_cnt} out tokens)"
        )
    structured = json.loads(raw_text) if raw_text else {}
    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured=structured,
        system_prompt=system_prompt,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )



async def run_cat4_haiku_reranker(
    rerank_payload: str,
    system_prompt: str,
    schema: dict[str, Any],
    api_key: str,
    max_tokens: int = 800,
    *,
    timeout_s: float = 45.0,
    max_retries: int | None = None,
    user_content: list[dict[str, Any]] | None = None,
) -> AnthropicRawResult:
    """Category 4 Stage-2 cross-chunk reranker on Haiku 5.5 with strict JSON schema.

    Optional keyword arguments (defaults keep the app's behaviour): `timeout_s`, `max_retries` (None = SDK
    default) and `user_content` — content blocks sent instead of `rerank_payload` (used by the quality rerun's
    cached full-corpus reranker; blocks may carry `cache_control`).
    """
    settings = get_settings()
    client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout_s}
    if max_retries is not None:
        client_kwargs["max_retries"] = max_retries
    client = anthropic.AsyncAnthropic(**client_kwargs)
    thinking_cfg: dict[str, str] = {"type": "disabled"}
    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "endpoint": "messages.create",
        "thinking": thinking_cfg,
        "output_config": {"format": {"type": "json_schema"}},
    }

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        settings.anthropic_haiku_model,
        ["claude-haiku-5-5", "claude-haiku-4-5"],
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_prompt,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": schema,
            }
        },
        messages=[{"role": "user", "content": user_content if user_content is not None else rerank_payload}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    raw_text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    if getattr(resp, "stop_reason", None) == "max_tokens":
        out_cnt = int(getattr(resp.usage, "output_tokens", 0) or 0)
        raise RuntimeError(
            f"Category 4 Haiku reranker hit max_tokens={max_tokens} ({out_cnt} out tokens)"
        )
    structured = json.loads(raw_text) if raw_text else {}
    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured=structured,
        system_prompt=system_prompt,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


async def run_cat4_rag_synthesis(
    system_prompt: str,
    user_question: str,
    documents_for_blocks: list[dict[str, Any]] | None,
    uncached_corpus_text: str | None,
    use_prefix_cache: bool,
    api_key: str,
    max_tokens: int = 2048,
    *,
    timeout_s: float = 90.0,
    max_retries: int | None = None,
    raise_on_max_tokens: bool = True,
) -> AnthropicRawResult:
    """Category 4 Sonnet 5.5 RAG synthesis supporting native DocumentBlocks + citations + cache_control.

    Optional keyword arguments (defaults keep the app's behaviour): `timeout_s`, `max_retries` (None = SDK
    default) and `raise_on_max_tokens` — False returns a truncated answer with `stop_reason="max_tokens"`
    instead of raising (used by the quality rerun, which records every answer).
    """
    settings = get_settings()
    client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout_s}
    if max_retries is not None:
        client_kwargs["max_retries"] = max_retries
    client = anthropic.AsyncAnthropic(**client_kwargs)
    thinking_cfg: dict[str, str] = {"type": "between_tools"}

    if documents_for_blocks is not None:
        user_content: list[dict[str, Any]] = []
        last_idx = len(documents_for_blocks) - 1
        for idx, doc in enumerate(documents_for_blocks):
            block: dict[str, Any] = {
                "type": "document",
                "title": doc["block_title"],
                "context": doc["block_context"],
                "source": {
                    "type": "text",
                    "media_type": "text/plain",
                    "data": doc["data"],
                },
                "citations": {"enabled": True},
            }
            if use_prefix_cache and idx == last_idx:
                block["cache_control"] = {"type": "ephemeral"}
            user_content.append(block)
        user_content.append({"type": "text", "text": user_question})
        messages_arg: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
    else:
        messages_arg = [
            {
                "role": "user",
                "content": (
                    f"=== DEAL ROOM CORPUS ===\n{uncached_corpus_text or ''}\n\n"
                    f"=== ANALYST DUE-DILIGENCE QUESTION ===\n{user_question}"
                ),
            }
        ]

    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "endpoint": "messages.create",
        "thinking": thinking_cfg,
        "prefix_cache_enabled": use_prefix_cache,
        "native_document_citations": documents_for_blocks is not None,
        "document_blocks_count": len(documents_for_blocks) if documents_for_blocks else 0,
    }

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        settings.anthropic_sonnet_model,
        ["claude-sonnet-5-5", "claude-sonnet-4-6"],
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_prompt,
        messages=messages_arg,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if raise_on_max_tokens and getattr(resp, "stop_reason", None) == "max_tokens":
        out_cnt = int(getattr(resp.usage, "output_tokens", 0) or 0)
        raise RuntimeError(
            f"Category 4 synthesis hit max_tokens={max_tokens} ({out_cnt} out tokens)"
        )

    parts: list[str] = []
    segments: list[dict[str, Any]] = []
    citations_out: list[dict[str, Any]] = []
    cite_key_to_num: dict[tuple[str, int, int], int] = {}

    for block in resp.content:
        if getattr(block, "type", None) != "text":
            continue
        txt = getattr(block, "text", "") or ""
        parts.append(txt)
        seg_cite_nums: list[int] = []
        raw_cits = getattr(block, "citations", None) or []
        if documents_for_blocks is not None and raw_cits:
            for cit in raw_cits:
                cdict = cit.model_dump() if hasattr(cit, "model_dump") else dict(cit)
                doc_idx = int(cdict.get("document_index", -1))
                if 0 <= doc_idx < len(documents_for_blocks):
                    meta = documents_for_blocks[doc_idx]
                    s_raw = int(cdict.get("start_char_index") or 0)
                    e_raw = int(cdict.get("end_char_index") or s_raw)
                    offset = int(meta.get("doc_char_offset") or 0)
                    doc_s = offset + s_raw
                    doc_e = offset + e_raw
                    dedup_key = (str(meta["doc_id"]), doc_s, doc_e)
                    if dedup_key not in cite_key_to_num:
                        cnum = len(citations_out) + 1
                        cite_key_to_num[dedup_key] = cnum
                        citations_out.append(
                            {
                                "cite_number": cnum,
                                "doc_id": str(meta["doc_id"]),
                                "document_title": str(
                                    cdict.get("document_title") or meta["block_title"]
                                ),
                                "clause_ref": str(meta.get("clause_ref") or ""),
                                "cited_text": str(cdict.get("cited_text") or ""),
                                "start_char_index": doc_s,
                                "end_char_index": doc_e,
                            }
                        )
                    cnum_found = cite_key_to_num[dedup_key]
                    if cnum_found not in seg_cite_nums:
                        seg_cite_nums.append(cnum_found)
        segments.append({"text": txt, "cite_numbers": seg_cite_nums})

    # CRITICAL: Join TextBlocks with empty string to avoid breaking sentences around citations
    raw_text = "".join(parts).strip()
    if not segments and raw_text:
        segments = [{"text": raw_text, "cite_numbers": []}]

    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured={
            "mode": "cat4_rag_synthesis",
            "segments": segments,
            "citations": citations_out,
        },
        system_prompt=system_prompt,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


def _serialize_content_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for b in blocks:
        b_type = getattr(b, "type", None)
        if b_type == "thinking":
            serialized.append(
                {
                    "type": "thinking",
                    "thinking": getattr(b, "thinking", ""),
                    "signature": getattr(b, "signature", ""),
                }
            )
        elif b_type == "redacted_thinking":
            serialized.append(
                {
                    "type": "redacted_thinking",
                    "data": getattr(b, "data", ""),
                }
            )
        elif b_type == "tool_use":
            serialized.append(
                {
                    "type": "tool_use",
                    "id": getattr(b, "id", ""),
                    "name": getattr(b, "name", ""),
                    "input": dict(getattr(b, "input", {}) or {}),
                }
            )
        elif b_type == "text":
            serialized.append(
                {
                    "type": "text",
                    "text": getattr(b, "text", ""),
                }
            )
    return serialized


async def run_cat5_tool_loop_step(
    *,
    model_tier: str,
    system_text: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    use_prefix_cache: bool,
    api_key: str,
    max_tokens: int = 2048,
    timeout_s: float = 60.0,
) -> AnthropicRawResult:
    """Execute one LLM step inside Category 5 SQLite ERP agent tool-use loop."""
    settings = get_settings()
    is_sonnet = "sonnet" in model_tier
    primary_model = settings.anthropic_sonnet_model if is_sonnet else settings.anthropic_haiku_model
    fallback_models = (
        ["claude-sonnet-5-5", "claude-sonnet-4-6"]
        if is_sonnet
        else ["claude-haiku-5-5", "claude-haiku-4-5"]
    )
    thinking_cfg: dict[str, str] = (
        {"type": "between_tools"} if is_sonnet else {"type": "disabled"}
    )
    system_arg: Any = (
        [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if use_prefix_cache
        else system_text
    )

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)
    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "endpoint": "messages.create",
        "thinking": thinking_cfg,
        "prefix_cache_enabled": use_prefix_cache,
        "tools_count": len(tools),
    }

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        primary_model,
        fallback_models,
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_arg,
        tools=tools,
        messages=messages,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    blocks_serialized = _serialize_content_blocks(list(resp.content))
    text_parts = [b["text"] for b in blocks_serialized if b["type"] == "text" and b["text"]]
    thinking_parts = [
        b["thinking"] for b in blocks_serialized if b["type"] == "thinking" and b.get("thinking")
    ]
    tool_uses = [b for b in blocks_serialized if b["type"] == "tool_use"]

    raw_text = "\n".join(text_parts).strip()
    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured={
            "assistant_blocks": blocks_serialized,
            "tool_uses": tool_uses,
            "thinking_text": "\n".join(thinking_parts).strip(),
        },
        system_prompt=system_text,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )


async def run_cat6_swarm_agent_call(
    *,
    model_tier: str,
    shared_repo_prefix: str,
    role_instructions: str,
    messages: list[dict[str, Any]],
    use_prefix_cache: bool,
    api_key: str,
    max_tokens: int = 3200,
    timeout_s: float = 120.0,
) -> AnthropicRawResult:
    """Execute one sub-agent call for Category 6 (isolated prefix-cached vs shared omnibus bus)."""
    settings = get_settings()
    is_sonnet = "sonnet" in model_tier
    primary_model = settings.anthropic_sonnet_model if is_sonnet else settings.anthropic_haiku_model
    fallback_models = (
        ["claude-sonnet-5-5", "claude-sonnet-4-6"]
        if is_sonnet
        else ["claude-haiku-5-5", "claude-haiku-4-5"]
    )
    thinking_cfg: dict[str, str] = (
        {"type": "between_tools"} if is_sonnet else {"type": "disabled"}
    )
    if use_prefix_cache:
        system_arg: Any = [
            {
                "type": "text",
                "text": shared_repo_prefix,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": role_instructions,
            },
        ]
    else:
        system_arg = role_instructions

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)
    request_params: dict[str, Any] = {
        "max_tokens": max_tokens,
        "endpoint": "messages.create",
        "thinking": thinking_cfg,
        "prefix_cache_enabled": use_prefix_cache,
    }

    t0 = time.perf_counter()
    used_model, resp = await _create_with_fallback(
        client,
        primary_model,
        fallback_models,
        max_tokens=max_tokens,
        thinking=thinking_cfg,
        system=system_arg,
        messages=messages,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    blocks_serialized = _serialize_content_blocks(list(resp.content))
    text_parts = [b["text"] for b in blocks_serialized if b["type"] == "text" and b["text"]]
    raw_text = "\n".join(text_parts).strip()
    in_tok, out_tok, c_write, c_read, think_tok = _extract_usage_tokens(resp.usage)

    return AnthropicRawResult(
        model_id=used_model,
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_tokens=c_write,
        cache_read_tokens=c_read,
        raw_text=raw_text,
        structured={"role_instructions": role_instructions[:400]},
        system_prompt=role_instructions,
        request_params=request_params,
        stop_reason=getattr(resp, "stop_reason", None),
        thinking_tokens=think_tok,
    )
