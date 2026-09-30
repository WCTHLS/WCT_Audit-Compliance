"""
Risk Factors formatting and SHAP explainability parser for AI Summary Service.
Formats machine learning risk scores and SHAP feature attributions into
human-readable investigator summaries without LLM hallucination.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from evidence_lookup.models import RiskFactorsData


class ParsedRiskSummary(BaseModel):
    """Structured breakdown of ML risk score and SHAP attributions."""
    risk_score: Optional[int] = None
    confidence_level: Optional[float] = None
    model_name: Optional[str] = None
    top_factor_name: Optional[str] = None
    top_shap_value: Optional[float] = None
    formatted_summary: str = ""
    bullet_points: List[str] = Field(default_factory=list)


def format_factor_value(val: Any, value_type: Optional[str] = None) -> str:
    """Format factor value based on value_type."""
    if val is None:
        return ""
    vt = (value_type or "").lower().strip()
    if vt == "rate":
        if isinstance(val, (int, float)):
            return f"{val * 100:.1f}%"
    elif vt == "rate_change":
        if isinstance(val, (int, float)):
            sign = "+" if val > 0 else ""
            return f"{sign}{val * 100:.1f} pts"
    elif vt == "binary":
        if val in (1, 1.0, "1", "1.0", True):
            return "Yes"
        elif val in (0, 0.0, "0", "0.0", False):
            return "No"
        return str(val)
    elif vt == "count":
        if isinstance(val, (int, float)):
            return str(int(val))
    elif vt == "days":
        if isinstance(val, (int, float)):
            n_str = str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)
            return f"{n_str} days"
    elif vt == "currency":
        if isinstance(val, (int, float)):
            n_str = str(int(val)) if isinstance(val, float) and val.is_integer() else f"{val:,.2f}"
            return f"${n_str}"
    elif vt == "distance_miles":
        if isinstance(val, (int, float)):
            n_str = str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)
            return f"{n_str} miles"
    elif vt == "score":
        return str(val)

    # missing/other -> number as given (NEVER guess percent from 0-1 range)
    return str(val)


def format_shap_value(shap: Any) -> str:
    """Format SHAP value preserving sign and adding (mitigating) for negatives."""
    if shap is None:
        return ""
    try:
        val = float(shap)
    except (ValueError, TypeError):
        return str(shap)

    if val < 0:
        return f"{val:.2f} (mitigating)"
    elif val > 0:
        return f"+{val:.2f}"
    else:
        return "+0.00"


def format_risk_factors_summary(
    risk_data: Union[RiskFactorsData, Dict[str, Any], Any],
    max_factors: int = 10,
) -> ParsedRiskSummary:
    """
    Parses RiskFactorsData and formats top contributors ranked by SHAP value.
    Omits missing fields instead of inventing hardcoded defaults.
    """
    if not risk_data:
        return ParsedRiskSummary()

    # Extract metadata
    if hasattr(risk_data, "model_metadata"):
        metadata = getattr(risk_data, "model_metadata", {}) or {}
    elif isinstance(risk_data, dict):
        metadata = risk_data.get("model_metadata", {})
    else:
        metadata = {}

    risk_score = metadata.get("risk_score")
    if risk_score is None and isinstance(risk_data, dict):
        risk_score = risk_data.get("risk_score")

    confidence = metadata.get("confidence_level")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = None

    model_name = metadata.get("model_name")

    # Extract risk factors list
    raw_factors: List[Any] = []
    if hasattr(risk_data, "risk_factors"):
        raw_factors = getattr(risk_data, "risk_factors", [])
    elif isinstance(risk_data, dict):
        raw_factors = risk_data.get("risk_factors", [])

    factors: List[Dict[str, Any]] = []
    for item in raw_factors:
        if isinstance(item, dict):
            factors.append(item)
        elif hasattr(item, "model_dump"):
            factors.append(item.model_dump())
        else:
            factors.append({
                "factor_name": getattr(item, "factor_name", "UNKNOWN"),
                "feature_value": getattr(item, "feature_value", None),
                "benchmark_median": getattr(item, "benchmark_median", None),
                "shap_value": getattr(item, "shap_value", 0.0),
                "value_type": getattr(item, "value_type", None),
                "description": getattr(item, "description", ""),
            })

    # Sort factors by SHAP value descending
    factors.sort(key=lambda x: float(x.get("shap_value", 0.0)), reverse=True)

    top_name = factors[0].get("factor_name") if factors else None
    top_shap = float(factors[0].get("shap_value", 0.0)) if factors else None

    bullets: List[str] = []
    for idx, f in enumerate(factors[:max_factors], 1):
        desc = f.get("description", "")
        shap_val = f.get("shap_value")
        feat_val = f.get("feature_value")
        bench_med = f.get("benchmark_median")
        v_type = f.get("value_type")

        val_str = format_factor_value(feat_val, v_type)
        bench_str = format_factor_value(bench_med, v_type) if (v_type or "").lower().strip() != "binary" else ""
        shap_str = format_shap_value(shap_val)

        parts = []
        if val_str:
            parts.append(f"value {val_str}")
        if bench_str:
            parts.append(f"benchmark {bench_str}")
        if shap_str:
            parts.append(f"SHAP {shap_str}")

        paren = f" ({', '.join(parts)})" if parts else ""
        bullets.append(f"  {idx}. {desc}{paren}")

    # Build primary summary text
    meta_parts = []
    if model_name:
        meta_parts.append(f"model {model_name}")
    if confidence is not None:
        meta_parts.append(f"confidence {confidence:.0%}")
    meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""

    summary_lines = []
    if risk_score is not None:
        summary_lines.append(f"Risk score: {risk_score}/1000{meta_str}")
    if bullets:
        summary_lines.append("Key risk factors (ranked by contribution):")
        summary_lines.extend(bullets)

    summary_text = "\n".join(summary_lines)

    return ParsedRiskSummary(
        risk_score=risk_score,
        confidence_level=confidence,
        model_name=model_name,
        top_factor_name=top_name,
        top_shap_value=top_shap,
        formatted_summary=summary_text,
        bullet_points=bullets,
    )


def format_risk_summary_text(risk_data: Union[RiskFactorsData, Dict[str, Any], Any]) -> str:
    """Convenience helper returning the formatted summary string."""
    return format_risk_factors_summary(risk_data).formatted_summary
