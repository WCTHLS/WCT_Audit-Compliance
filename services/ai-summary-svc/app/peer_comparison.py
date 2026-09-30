"""
Dedicated Peer Comparison module for AI Summary Service.
Performs deterministic statistical calculations on provider peer metrics
without LLM hallucinations or guessing.
"""

from typing import Any, Dict, Optional, Union
from pydantic import BaseModel
from event_contracts import PeerComparisonData
from evidence_lookup.models import PeerComparisonDetailData


class PeerMetricsResult(BaseModel):
    """Calculated peer comparison statistical metrics."""
    specialty: Optional[str] = None
    region: Optional[str] = None
    cohort_size: Optional[int] = None
    metric_name: Optional[str] = None
    provider_value: Optional[float] = None
    peer_median: Optional[float] = None
    computed_percentile: Optional[float] = None
    ratio_to_median: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None
    max: Optional[float] = None
    narrative: str


def compute_peer_metrics(
    peer_data: Any,
) -> Optional[PeerMetricsResult]:
    """
    Extracts statistical metrics from peer comparison data without inventing defaults.
    Returns None if input is unrecognised or empty.
    """
    if not peer_data:
        return None

    if isinstance(peer_data, dict):
        d = peer_data
        stats = d.get("statistics") or {}
        specialty = d.get("specialty")
        region = d.get("region")
        cohort_size = d.get("cohort_size")
        metric_name = d.get("metric_name")
        provider_val = d.get("provider_value", d.get("provider_metric_value"))
        peer_med = stats.get("median", d.get("peer_median"))
        percentile = stats.get("computed_percentile", d.get("peer_percentile", d.get("computed_percentile")))
        ratio = stats.get("ratio_to_median", d.get("ratio_to_median"))
        p95 = stats.get("p95")
        p99 = stats.get("p99")
        max_val = stats.get("max")
    elif hasattr(peer_data, "model_dump"):
        d = peer_data.model_dump()
        stats = d.get("statistics") or {}
        specialty = d.get("specialty")
        region = d.get("region")
        cohort_size = d.get("cohort_size")
        metric_name = d.get("metric_name")
        provider_val = d.get("provider_value", d.get("provider_metric_value"))
        peer_med = stats.get("median", d.get("peer_median"))
        percentile = stats.get("computed_percentile", d.get("peer_percentile", d.get("computed_percentile")))
        ratio = stats.get("ratio_to_median", d.get("ratio_to_median"))
        p95 = stats.get("p95")
        p99 = stats.get("p99")
        max_val = stats.get("max")
    elif isinstance(peer_data, (PeerComparisonData, PeerComparisonDetailData)):
        specialty = getattr(peer_data, "specialty", None)
        region = getattr(peer_data, "region", None)
        cohort_size = getattr(peer_data, "cohort_size", None)
        metric_name = getattr(peer_data, "metric_name", None)
        provider_val = getattr(peer_data, "provider_value", getattr(peer_data, "provider_metric_value", None))
        stats = getattr(peer_data, "statistics", None)
        peer_med = getattr(stats, "median", getattr(peer_data, "peer_median", None)) if stats else getattr(peer_data, "peer_median", None)
        percentile = getattr(stats, "computed_percentile", getattr(peer_data, "peer_percentile", None)) if stats else getattr(peer_data, "peer_percentile", None)
        ratio = getattr(stats, "ratio_to_median", getattr(peer_data, "ratio_to_median", None)) if stats else getattr(peer_data, "ratio_to_median", None)
        p95 = getattr(stats, "p95", None) if stats else None
        p99 = getattr(stats, "p99", None) if stats else None
        max_val = getattr(stats, "max", None) if stats else None
    else:
        return None

    # If all core metrics are missing, return None
    if provider_val is None and peer_med is None and not specialty and not metric_name:
        return None

    # Cast numeric values safely if present
    def _to_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    provider_val = _to_float(provider_val)
    peer_med = _to_float(peer_med)
    percentile = _to_float(percentile)
    ratio = _to_float(ratio)
    p95 = _to_float(p95)
    p99 = _to_float(p99)
    max_val = _to_float(max_val)

    if ratio is None and provider_val is not None and peer_med is not None and peer_med > 0:
        ratio = round(provider_val / peer_med, 2)

    # Build bracket statistics: (<ratio_to_median>x median, <computed_percentile> percentile, p95 <p95>, p99 <p99>, max <max>)
    bracket_parts = []
    if ratio is not None:
        bracket_parts.append(f"{ratio}x median")
    if percentile is not None:
        bracket_parts.append(f"{percentile} percentile")
    if p95 is not None:
        bracket_parts.append(f"p95 {p95}")
    if p99 is not None:
        bracket_parts.append(f"p99 {p99}")
    if max_val is not None:
        bracket_parts.append(f"max {max_val}")

    bracket_str = f" ({', '.join(bracket_parts)})" if bracket_parts else ""

    across_parts = []
    if cohort_size is not None:
        across_parts.append(f"{cohort_size}")
    if specialty:
        across_parts.append(specialty)
    across_str = f" across {' '.join(across_parts)} peers" if across_parts else ""
    in_region_str = f" in {region}" if region else ""

    m_name = metric_name or ""
    pv_str = f"{provider_val}" if provider_val is not None else ""
    med_str = f" vs peer median {peer_med}" if peer_med is not None else ""

    prefix = f"{m_name} {pv_str}".strip()
    narrative = f"Peer comparison: {prefix}{med_str}{bracket_str}{across_str}{in_region_str}.".strip()

    return PeerMetricsResult(
        specialty=specialty,
        region=region,
        cohort_size=cohort_size,
        metric_name=metric_name,
        provider_value=provider_val,
        peer_median=peer_med,
        computed_percentile=percentile,
        ratio_to_median=ratio,
        p95=p95,
        p99=p99,
        max=max_val,
        narrative=narrative,
    )


def compute_peer_narrative(
    peer_data: Any,
) -> Optional[str]:
    """Convenience helper returning just the narrative string or None."""
    res = compute_peer_metrics(peer_data)
    return res.narrative if res else None
