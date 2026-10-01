"""
Exclusion screening service logic and entity extraction pipeline.
Resolves evidence pointers and performs multi-entity screening against exclusion records.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.models import ExclusionRecord
from src.matcher import match_entity, normalize_text, normalize_business_name, clean_npi
from src.schemas import (
    ScreenRequest,
    ScreenResponse,
    EntityScreeningResult,
    ExclusionRecordDetail,
    HealthResponse,
)

try:
    from evidence_lookup import EvidenceLookupClient
    _EVIDENCE_CLIENT = EvidenceLookupClient()
except Exception:
    _EVIDENCE_CLIENT = None


class EntityToScreen:
    def __init__(
        self,
        role: str,
        name: Optional[str] = None,
        npi: Optional[str] = None,
        is_organization: bool = False,
    ):
        self.role = role
        self.name = name or ""
        self.npi = clean_npi(npi)
        self.is_organization = is_organization


def extract_entities_from_case(req: ScreenRequest) -> List[EntityToScreen]:
    """
    Extracts providers, facilities, and fraud ring entities from the case and evidence pointers.
    """
    entities: List[EntityToScreen] = []
    
    # Try resolving via EvidenceLookupClient if pointers exist
    clinical_bundle = None
    risk_factors_data = None
    
    if req.evidence_pointers and _EVIDENCE_CLIENT:
        try:
            clinical_bundle = _EVIDENCE_CLIENT.resolve_clinical_evidence(req.evidence_pointers)
        except Exception:
            clinical_bundle = None
            
        try:
            risk_factors_data = _EVIDENCE_CLIENT.resolve_risk_factors(req.evidence_pointers)
        except Exception:
            risk_factors_data = None

    # 1. Ordering / Rendering Physician
    doctor_name = req.doctor_name
    doctor_npi = req.doctor_npi
    if clinical_bundle and hasattr(clinical_bundle, "extracted_entities") and clinical_bundle.extracted_entities:
        ext = clinical_bundle.extracted_entities
        if ext.get("doctor_name"):
            doctor_name = ext.get("doctor_name")
        if ext.get("doctor_npi"):
            doctor_npi = ext.get("doctor_npi")
    
    if doctor_name or doctor_npi:
        entities.append(EntityToScreen(
            role="ordering_provider",
            name=doctor_name,
            npi=doctor_npi,
            is_organization=False,
        ))

    # 2. Facility / Supplier
    facility_name = req.facility_name
    facility_npi = req.facility_npi
    if clinical_bundle and hasattr(clinical_bundle, "extracted_entities") and clinical_bundle.extracted_entities:
        ext = clinical_bundle.extracted_entities
        if ext.get("facility_name"):
            facility_name = ext.get("facility_name")
        if ext.get("facility_npi"):
            facility_npi = ext.get("facility_npi")
            
    if facility_name or facility_npi:
        entities.append(EntityToScreen(
            role="facility",
            name=facility_name,
            npi=facility_npi,
            is_organization=True,
        ))

    # 3. Fraud Ring Entities (if flagged)
    if risk_factors_data and getattr(risk_factors_data, "fraud_ring_analysis", None):
        fra = risk_factors_data.fraud_ring_analysis
        flagged = getattr(fra, "flagged", False) or (isinstance(fra, dict) and fra.get("flagged", False))
        if flagged:
            ring_entities = getattr(fra, "entities", []) or (fra.get("entities", []) if isinstance(fra, dict) else [])
            for rent in ring_entities:
                ename = rent.name if hasattr(rent, "name") else rent.get("name")
                enpi = rent.npi if hasattr(rent, "npi") else rent.get("npi")
                etype = rent.entity_type if hasattr(rent, "entity_type") else rent.get("entity_type", "Fraud Ring Entity")
                is_org = "Physician" not in str(etype) and "Doctor" not in str(etype)
                entities.append(EntityToScreen(
                    role=f"fraud_ring_{str(etype).lower().replace(' ', '_')}",
                    name=ename,
                    npi=enpi,
                    is_organization=is_org,
                ))

    # De-duplicate entities by NPI or Normalized Name
    deduped: List[EntityToScreen] = []
    seen_npis = set()
    seen_names = set()
    
    for ent in entities:
        if ent.npi and ent.npi in seen_npis:
            continue
        norm_n = normalize_text(ent.name)
        if norm_n and norm_n in seen_names:
            continue
        
        if ent.npi:
            seen_npis.add(ent.npi)
        if norm_n:
            seen_names.add(norm_n)
        deduped.append(ent)
        
    return deduped


def screen_case(db: Session, req: ScreenRequest) -> ScreenResponse:
    """
    Executes full screening workflow for the case against the database.
    """
    entities = extract_entities_from_case(req)
    results: List[EntityScreeningResult] = []
    
    worst_rank = 0  # 0: NO_MATCH, 1: POSSIBLE_MATCH, 2: MATCH
    rank_map = {"NO_MATCH": 0, "POSSIBLE_MATCH": 1, "MATCH": 2}
    
    for ent in entities:
        outcome, basis, matched_rec = match_entity(
            db=db,
            role=ent.role,
            name=ent.name,
            npi=ent.npi,
            is_organization=ent.is_organization,
        )
        
        rank = rank_map.get(outcome, 0)
        if rank > worst_rank:
            worst_rank = rank
            
        record_detail = None
        if matched_rec:
            record_detail = ExclusionRecordDetail(
                source=matched_rec.source,
                excl_type=matched_rec.excl_type,
                excl_date=matched_rec.excl_date.isoformat() if matched_rec.excl_date else None,
                specialty=matched_rec.specialty,
                last_name=matched_rec.last_name,
                first_name=matched_rec.first_name,
                bus_name=matched_rec.bus_name,
                npi=matched_rec.npi,
                city=matched_rec.city,
                state=matched_rec.state,
            )
            
        results.append(
            EntityScreeningResult(
                role=ent.role,
                name=ent.name,
                npi=ent.npi,
                result=outcome,
                match_basis=basis,
                record=record_detail,
            )
        )
        
    inv_rank = {0: "NO_MATCH", 1: "POSSIBLE_MATCH", 2: "MATCH"}
    overall_result = inv_rank[worst_rank]
    
    # Query snapshot metadata
    snapshots = {}
    sources = db.query(ExclusionRecord.source, func.count(ExclusionRecord.id)).group_by(ExclusionRecord.source).all()
    for s, _ in sources:
        snapshots[s] = "active"
        
    return ScreenResponse(
        case_id=req.case_id,
        overall_result=overall_result,
        screened_at=datetime.now(timezone.utc).isoformat(),
        list_snapshot=snapshots,
        results=results,
        requires_auditor_confirmation=(overall_result in ["MATCH", "POSSIBLE_MATCH"]),
    )


def get_health_status(db: Session) -> HealthResponse:
    """
    Returns system health and current dataset record counts.
    """
    counts = {}
    records = db.query(ExclusionRecord.source, func.count(ExclusionRecord.id)).group_by(ExclusionRecord.source).all()
    for source, cnt in records:
        counts[source] = cnt
        
    return HealthResponse(
        status="healthy",
        service="exclusion-screening-svc",
        record_counts=counts,
        snapshot_info={"status": "ready"},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
