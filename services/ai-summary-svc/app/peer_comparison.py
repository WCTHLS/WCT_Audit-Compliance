"""
Dedicated Peer Comparison module for AI Summary Service.
Performs deterministic statistical calculations on provider peer metrics
without LLM hallucinations or guessing.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel
from event_contracts import PeerComparisonData
from evidence_lookup.models import PeerComparisonDetailData

logger = logging.getLogger("ai_summary.peer_comparison")


def resolve_repo_root() -> Path:
    """Find repository root (directory containing mock-data, libs, or .git)."""
    env_root = os.getenv("REPO_ROOT")
    if env_root and Path(env_root).exists():
        return Path(env_root).resolve()
    if Path("/app/mock-data").exists():
        return Path("/app").resolve()
    curr = Path(__file__).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / "mock-data").exists() or (parent / ".git").exists():
            return parent.resolve()
    return Path.cwd().resolve()


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
    Loads full fixture file from fixture_ref resolved relative to repo root if available.
    Returns None if input is unrecognised or empty.
    """
    if not peer_data:
        return None

    d: Dict[str, Any] = {}

    if isinstance(peer_data, dict):
        d = dict(peer_data)
        fixture_ref = d.get("fixture_ref")
        if fixture_ref:
            repo_root = resolve_repo_root()
            target_path = (repo_root / fixture_ref).resolve()
            if target_path.exists() and target_path.is_file():
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                except Exception as e:
                    logger.warning("Error reading peer comparison fixture at '%s': %s", target_path, e)
            else:
                logger.warning("Peer comparison fixture not found at '%s'. Falling back to event summary.", target_path)

    elif isinstance(peer_data, str) and (peer_data.endswith(".json") or "mock-data" in peer_data):
        repo_root = resolve_repo_root()
        target_path = (repo_root / peer_data).resolve()
        if target_path.exists() and target_path.is_file():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
            except Exception as e:
                logger.warning("Error reading peer comparison fixture at '%s': %s", target_path, e)
                return None
        else:
            logger.warning("Peer comparison fixture not found at '%s'.", target_path)
            return None

    elif hasattr(peer_data, "model_dump"):
        d = peer_data.model_dump()
        fixture_ref = d.get("fixture_ref")
        if fixture_ref:
            repo_root = resolve_repo_root()
            target_path = (repo_root / fixture_ref).resolve()
            if target_path.exists() and target_path.is_file():
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                except Exception as e:
                    logger.warning("Error reading peer comparison fixture at '%s': %s", target_path, e)
            else:
                logger.warning("Peer comparison fixture not found at '%s'. Falling back to event summary.", target_path)

    elif isinstance(peer_data, (PeerComparisonData, PeerComparisonDetailData)):
        d = {
            "specialty": getattr(peer_data, "specialty", None),
            "region": getattr(peer_data, "region", None),
            "cohort_size": getattr(peer_data, "cohort_size", None),
            "metric_name": getattr(peer_data, "metric_name", None),
            "provider_value": getattr(peer_data, "provider_value", getattr(peer_data, "provider_metric_value", None)),
        }
        stats_obj = getattr(peer_data, "statistics", None)
        if stats_obj:
            d["statistics"] = stats_obj.model_dump() if hasattr(stats_obj, "model_dump") else dict(stats_obj)
        else:
            d["peer_median"] = getattr(peer_data, "peer_median", None)
            d["peer_percentile"] = getattr(peer_data, "peer_percentile", None)
            d["ratio_to_median"] = getattr(peer_data, "ratio_to_median", None)
    else:
        return None

    if not d:
        return None

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

    # If all core metrics are missing, return None
    if provider_val is None and peer_med is None and not specialty and not metric_name:
        return None

    # Cast numeric values safely if present
    def _to_float(v: Any) -> Optional[float]:
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

    is_percent_metric = False
    m_name = (metric_name or "").strip()
    if m_name.endswith("(%)"):
        is_percent_metric = True
        m_name = m_name[:-3].strip()

    suffix = "%" if is_percent_metric else ""

    pv_str = f"{provider_val:.1f}{suffix}" if provider_val is not None else ""
    med_str = f"{peer_med:.1f}{suffix}" if peer_med is not None else ""

    # Build bracket statistics: (<ratio_to_median>x median, <computed_percentile> percentile, p95 <p95>, p99 <p99>, max <max>)
    bracket_parts = []
    if ratio is not None:
        bracket_parts.append(f"{ratio}x median")
    if percentile is not None:
        bracket_parts.append(f"{percentile:.1f} percentile")
    if p95 is not None:
        bracket_parts.append(f"p95 {p95:.1f}{suffix}")
    if p99 is not None:
        bracket_parts.append(f"p99 {p99:.1f}{suffix}")
    if max_val is not None:
        bracket_parts.append(f"max {max_val:.1f}{suffix}")

    bracket_str = f" ({', '.join(bracket_parts)})" if bracket_parts else ""

    across_parts = []
    if cohort_size is not None:
        across_parts.append(f"{cohort_size}")
    if specialty:
        across_parts.append(str(specialty).strip())
    across_str = f" across {' '.join(across_parts)} peers" if across_parts else ""
    in_region_str = f" in {region}" if region else ""

    if m_name and pv_str:
        prefix = f"{m_name} {pv_str}"
    elif m_name:
        prefix = m_name
    else:
        prefix = pv_str

    if not prefix and not med_str and not bracket_str:
        return None

    med_clause = f" vs peer median {med_str}" if med_str else ""
    narrative = f"Peer comparison: {prefix}{med_clause}{bracket_str}{across_str}{in_region_str}.".strip()

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
