"""
Core Summarizer engine for AI Summary Service.

Same public API as before — SummarizeRequest / SummarizeResponse / 
summarizer_engine — so routes and the React frontend keep working.
The internals are now one LLM call over flattened case JSON.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from evidence_lookup import EvidenceLookupClient, EvidenceLookupError
from app.case_narrative import (
    SYSTEM_PROMPT,
    build_prompt,
    build_risk_peer_section,
    check_numbers,
)
from llm_client import llm_client
from src.config import settings

logger = logging.getLogger("ai_summary.summarizer")

# Initialize HuggingFace / Fast Tokenizer if local model cache exists
_tokenizer = None
try:
    from tokenizers import Tokenizer

    _tok_candidates = [
        Path.home() / ".foundry" / "cache" / "models" / "Microsoft" / "qwen2.5-7b-instruct-openvino-gpu-2" / "v2" / "tokenizer.json",
        Path.home() / ".foundry" / "cache" / "models" / "Microsoft" / "qwen2.5-7b-instruct-openvino-npu-4" / "v4" / "tokenizer.json",
    ]
    for _tok_path in _tok_candidates:
        if _tok_path.exists():
            _tokenizer = Tokenizer.from_file(str(_tok_path))
            break
except Exception as e:
    logger.warning("Could not initialize local tokenizer: %s", e)
    _tokenizer = None


def estimate_tokens(prompt: str, system_prompt: str = SYSTEM_PROMPT) -> int:
    """
    Count or estimate input tokens for Qwen2.5 chat template.
    Uses exact tokenizer.json when available, otherwise falls back to chars / 3.8.
    """
    if _tokenizer is not None:
        try:
            full_chat = (
                f"<|im_start|>system\n{system_prompt}\n/no_think<|im_end|>\n"
                f"<|im_start|>user\n{prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
            return len(_tokenizer.encode(full_chat).ids)
        except Exception:
            pass
    total_chars = len(system_prompt) + len(prompt)
    return int(total_chars / 3.8)


class SummarizeRequest(BaseModel):
    """Input payload for POST /summarize. Unchanged."""

    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Unique case identifier")
    claim_ref: str = Field(..., description="Claim reference ID")
    risk_score: int = Field(default=850, ge=100, le=1000)
    flagged_reason: Optional[str] = None
    evidence_pointers: Optional[Dict[str, Any]] = None
    service_date: Optional[str] = None


class SummarizeResponse(BaseModel):
    """
    Response for POST /summarize.

    Field names are preserved so existing callers don't break. The fields that
    used to carry parsed subsections are kept but now return empty strings —
    the narrative is a single block of prose and is not split up.
    """

    model_config = ConfigDict(extra="ignore")

    case_id: str
    claim_ref: str
    clinical_summary: str            # the narrative
    confidence_score: float
    model_version: str
    validation_warnings: List[str] = Field(default_factory=list)

    # Retained for backward compatibility with existing consumers.
    bottom_line: str = ""
    encounter_as_documented: str = ""
    line_by_line_assessment: str = ""
    evidence_required: str = ""
    line_status_map: Dict[str, str] = Field(default_factory=dict)
    risk_factors_summary: str = ""
    peer_comparison_narrative: str = ""
    validation_result: str = "PASSED"
    releasable: bool = True
    checks_executed: List[str] = Field(default_factory=list)


def normalise_markdown(text: str) -> str:
    """
    Normalise markdown in LLM text:
    - Removes '**' and '__' wrappers
    - Removes leading '#' characters from lines
    - Keeps the text itself unchanged
    """
    if not text:
        return text
    cleaned_lines = []
    for line in text.split("\n"):
        l = line.replace("**", "").replace("__", "")
        l = re.sub(r"^\s*#+\s*", "", l)
        cleaned_lines.append(l)
    return "\n".join(cleaned_lines)


class CaseSummarizer:
    """Loads case evidence and generates a narrative summary."""

    def __init__(self, evidence_client: Optional[EvidenceLookupClient] = None):
        self.evidence_client = evidence_client or EvidenceLookupClient()

    @staticmethod
    def _has_meaningful_evidence(case: Dict[str, Any]) -> bool:
        meaningful_keys = (
            "clinical",
            "risk",
            "peer",
            "flags",
            "drg_validation",
        )
        return any(bool(case.get(key)) for key in meaningful_keys)

    def _load_case(self, request: SummarizeRequest) -> Dict[str, Any]:
        """
        Resolve whatever evidence artifacts exist. Anything that fails to
        resolve is simply absent from the case dict and won't appear in the
        summary.
        """
        pointers = request.evidence_pointers or {}

        case: Dict[str, Any] = {
            "event": {
                "case_id": request.case_id,
                "claim_ref": request.claim_ref,
                "risk_score": request.risk_score,
                "flagged_reason": request.flagged_reason,
            }
        }
        if request.service_date:
            case["event"]["service_date"] = request.service_date

        resolvers = {
            "clinical": ("clinical_evidence", self.evidence_client.resolve_clinical_evidence),
            "risk": ("risk_factors", self.evidence_client.resolve_risk_factors),
            "peer": ("peer_comparison", self.evidence_client.resolve_peer_comparison),
            "flags": ("claim_flags", self.evidence_client.resolve_claim_flags),
            "drg_validation": ("drg_validation", self.evidence_client.resolve_drg_validation),
        }

        for key, (pointer_name, resolve) in resolvers.items():
            if pointer_name not in pointers:
                continue
            try:
                model = resolve(pointers)
                if model:
                    case[key] = model.model_dump(mode="json")
            except EvidenceLookupError as e:
                logger.warning("Could not resolve %s: %s", pointer_name, e)

        # peer_comparison is sometimes inlined on the pointer itself
        if "peer" not in case and isinstance(pointers.get("peer_comparison"), dict):
            case["peer"] = pointers["peer_comparison"]

        return case

    async def summarize_case(self, request: SummarizeRequest) -> SummarizeResponse:
        logger.info("Summarizing case %s (claim %s)", request.case_id, request.claim_ref)

        case = self._load_case(request)
        active_model = settings.FOUNDRY_MODEL if settings.LLM_PROVIDER == "foundry" else settings.OLLAMA_MODEL
        model_version = f"{settings.LLM_PROVIDER}:{active_model}"

        if not self._has_meaningful_evidence(case):
            return SummarizeResponse(
                case_id=request.case_id,
                claim_ref=request.claim_ref,
                clinical_summary=(
                    "No usable evidence was available for this case, so no "
                    "summary could be produced. Manual review is required."
                ),
                confidence_score=0.0,
                model_version=model_version,
                validation_warnings=["No usable evidence resolved."],
                releasable=False,
                validation_result="NO DATA",
            )

        prompt = build_prompt(case)
        model_context_limit = getattr(settings, "MODEL_CONTEXT_LIMIT", 32768)
        output_tokens = getattr(settings, "OUTPUT_TOKENS", 1000)

        # Estimate/count input tokens for system prompt + user prompt
        estimated_input_tokens = estimate_tokens(prompt, SYSTEM_PROMPT)
        logger.info(
            "Case %s rendered CASE DATA length: %d chars | Estimated input tokens: %d | Output tokens: %d",
            request.case_id,
            len(prompt),
            estimated_input_tokens,
            output_tokens,
        )

        # Token Budget Guard: if input + output exceeds context limit - 100, do not call LLM
        if estimated_input_tokens + output_tokens > model_context_limit - 100:
            warning_msg = (
                f"Estimated input tokens ({estimated_input_tokens}) + {output_tokens} output tokens "
                f"exceeds model context limit ({model_context_limit - 100})"
            )
            logger.warning("Case %s input too large: %s", request.case_id, warning_msg)
            return SummarizeResponse(
                case_id=request.case_id,
                claim_ref=request.claim_ref,
                clinical_summary="",
                confidence_score=0.0,
                model_version=model_version,
                validation_warnings=[warning_msg],
                releasable=False,
                validation_result="INPUT_TOO_LARGE",
            )

        try:
            summary = await llm_client.complete(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                case_id=request.case_id,
                claim_ref=request.claim_ref,
                temperature=0.2,
                max_tokens=output_tokens,
            )
            summary = (summary or "").strip()
        except Exception as exc:
            logger.error("Case %s LLM completion error: %s", request.case_id, exc)
            return SummarizeResponse(
                case_id=request.case_id,
                claim_ref=request.claim_ref,
                clinical_summary="",
                confidence_score=0.0,
                model_version=model_version,
                validation_warnings=[str(exc)],
                releasable=False,
                validation_result="LLM_ERROR",
            )

        # Log actual prompt tokens if returned by provider
        actual_prompt_tokens = getattr(llm_client, "last_prompt_tokens", None)
        if actual_prompt_tokens is not None:
            logger.info(
                "Case %s prompt token accuracy: actual=%d, estimated=%d (diff=%d)",
                request.case_id,
                actual_prompt_tokens,
                estimated_input_tokens,
                actual_prompt_tokens - estimated_input_tokens,
            )

        warnings = check_numbers(summary, case)
        if getattr(llm_client, "last_finish_reason", None) == "length":
            logger.warning("Case %s summary truncated at token limit", request.case_id)
            warnings.append("Summary truncated at token limit")

        if warnings:
            logger.warning(
                "Case %s: %d warning(s) in summary validation: %s",
                request.case_id,
                len(warnings),
                warnings,
            )

        # Normalise markdown in LLM text before inserting risk/peer section
        norm_summary = normalise_markdown(summary)

        # Build and insert deterministic Risk and Peer Context section
        section = build_risk_peer_section(case)
        if section:
            lines = norm_summary.split("\n")
            insert_idx = None
            for idx, l in enumerate(lines):
                cleaned = l.strip()
                if re.match(r"^Auditor\s+Takeaway\b", cleaned, re.IGNORECASE):
                    insert_idx = idx
                    break
            if insert_idx is not None:
                before = "\n".join(lines[:insert_idx]).rstrip()
                after = "\n".join(lines[insert_idx:]).lstrip()
                if before:
                    assembled_summary = f"{before}\n\n{section}\n\n{after}"
                else:
                    assembled_summary = f"{section}\n\n{after}"
            else:
                assembled_summary = f"{norm_summary.rstrip()}\n\n{section}" if norm_summary.strip() else section
        else:
            assembled_summary = norm_summary

        # Extract risk part and peer line for response fields
        peer_line = ""
        risk_lines = []
        if section:
            for s_line in section.split("\n"):
                if s_line.startswith("Peer comparison:"):
                    peer_line = s_line
                elif not s_line.startswith("Risk and Peer Context:"):
                    risk_lines.append(s_line)
        risk_part = "\n".join(risk_lines).strip()

        confidence = float(
            (case.get("risk") or {}).get("model_metadata", {}).get("confidence_level", 0.0)
        )

        return SummarizeResponse(
            case_id=request.case_id,
            claim_ref=request.claim_ref,
            clinical_summary=assembled_summary,
            confidence_score=confidence,
            model_version=model_version,
            validation_warnings=warnings,
            validation_result="PASSED" if not warnings else f"{len(warnings)} WARNING(S)",
            releasable=not bool(warnings),
            checks_executed=["number_check", "risk_peer_deterministic"],
            risk_factors_summary=risk_part,
            peer_comparison_narrative=peer_line,
        )


summarizer_engine = CaseSummarizer()

