"""Google Gemini Decisions API wrapper for Rung 3 (System-1, 0 Output Tokens)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
import httpx
from google import genai

from app.config import get_settings


@dataclass
class GeminiDecisionRawResult:
    model_id: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    structured_summary: dict[str, Any]
    decision_probabilities: dict[str, Any]
    request_questions: dict[str, Any] | None = None
    endpoint: str = "v1beta/decisions"


def _normalize_sdk_or_rest_answers(answers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize both google-genai Pydantic objects and raw REST dicts into uniform UI structs."""
    summary: dict[str, Any] = {}
    probs: dict[str, Any] = {}

    for q_id, ans in answers.items():
        if hasattr(ans, "model_dump"):
            data = ans.model_dump()
        elif isinstance(ans, dict):
            data = ans
        else:
            data = {}

        q_type = data.get("type")
        conf = round(float(data.get("confidence", 0.0) or 0.0), 4)

        if q_type == "choice" or "choice" in data:
            chosen = data.get("choice")
            raw_probs = data.get("probabilities") or {}
            summary[q_id] = chosen
            probs[q_id] = {
                "type": "choice",
                "value": chosen,
                "confidence": conf,
                "probabilities": {str(k): round(float(v), 4) for k, v in raw_probs.items()},
            }
        elif q_type == "score" or "score" in data:
            score_val = round(float(data.get("score", 0.0) or 0.0), 3)
            raw_probs = data.get("probabilities") or {}
            legend = data.get("legend") or {}
            summary[q_id] = score_val
            probs[q_id] = {
                "type": "score",
                "value": score_val,
                "confidence": conf,
                "probabilities": {str(k): round(float(v), 4) for k, v in raw_probs.items()},
                "legend": {str(k): str(v) for k, v in legend.items()},
            }
        elif q_type == "noul" or "noul" in data:
            p_true = round(float(data.get("noul", 0.0) or 0.0), 4)
            verdict = p_true >= 0.5
            summary[q_id] = verdict
            probs[q_id] = {
                "type": "noul",
                "value": verdict,
                "p_true": p_true,
                "confidence": conf,
            }

    return summary, probs


async def run_gemini_decision(
    payload_text: str,
    questions: dict[str, Any],
    api_key: str,
) -> GeminiDecisionRawResult:
    """Execute one-pass calibrated System-1 decisions with gemini-decision-1 (0 output tokens)."""
    settings = get_settings()
    model_id = settings.gemini_decision_model

    t0 = time.perf_counter()
    answers_raw: dict[str, Any] = {}
    input_tokens = 0
    output_tokens = 0

    try:
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        resp = await client.aio.decisions.create(
            model=model_id,
            input=payload_text,
            questions=questions,
        )
        answers_raw = dict(resp.answers or {})
        usage = getattr(resp, "usage", None)
        if usage is not None:
            input_tokens = int(
                getattr(usage, "total_input_tokens", None)
                or getattr(usage, "initial_input_tokens", None)
                or 0
            )
            output_tokens = int(getattr(usage, "total_output_tokens", 0) or 0)
    except Exception as sdk_exc:
        # Fallback to direct v1beta REST endpoint if SDK wrapper rejects beta transport
        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.post(
                "https://generativelanguage.googleapis.com/v1beta/decisions",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "input": payload_text,
                    "questions": questions,
                },
            )
            if r.status_code >= 400:
                raise RuntimeError(
                    f"Gemini Decisions API error ({r.status_code}): {r.text[:300]} (SDK note: {sdk_exc})"
                ) from sdk_exc
            body = r.json()
            answers_raw = body.get("answers") or {}
            usage = body.get("usage") or {}
            input_tokens = int(
                usage.get("total_input_tokens")
                or usage.get("initial_input_tokens")
                or 0
            )
            output_tokens = int(usage.get("total_output_tokens") or 0)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    if input_tokens <= 0:
        # Approximate input token count if preview endpoint omits usage metadata
        input_tokens = max(1, round(len(payload_text) / 3.8))

    summary, probs = _normalize_sdk_or_rest_answers(answers_raw)

    return GeminiDecisionRawResult(
        model_id=model_id,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        structured_summary=summary,
        decision_probabilities=probs,
        request_questions=questions,
        endpoint="v1beta/decisions",
    )
