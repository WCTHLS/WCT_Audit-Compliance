"""
Core Evidence Lookup Client.
Resolves case evidence_pointers into validated Pydantic evidence data models.
Supports local filesystem mock fixtures (POC) and is designed for seamless
extension to S3 / MinIO Object Storage in production.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, ValidationError

from evidence_lookup.models import (
    ClinicalEvidenceData,
    RiskFactorsData,
    PeerComparisonDetailData,
    ClaimFlagsData,
    DRGValidationData,
    FullEvidenceBundle,
)

logger = logging.getLogger("wct.evidence_lookup")


class EvidenceLookupError(Exception):
    """Base exception for evidence lookup operations."""
    pass


class EvidenceNotFoundError(EvidenceLookupError):
    """Raised when an evidence pointer cannot be resolved to an existing file or storage URI."""
    pass


class EvidenceParseError(EvidenceLookupError):
    """Raised when evidence content fails JSON parsing or schema validation."""
    pass


class EvidenceLookupClient:
    """
    Client for resolving healthcare case evidence pointers into structured data objects.
    """

    def __init__(self, base_dir: Optional[Union[Path, str]] = None):
        """
        Initializes the EvidenceLookupClient.
        :param base_dir: Optional root directory where mock fixtures are stored.
                         Defaults to discovering the workspace `mock-data/` directory.
        """
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            # Auto-detect workspace root mock-data directory
            curr = Path(__file__).resolve()
            # libs/evidence-lookup/evidence_lookup/client.py -> parents[3] is workspace root
            workspace_root = curr.parents[3]
            self.base_dir = (workspace_root / "mock-data").resolve()

    def _resolve_path(self, pointer: str) -> Path:
        """
        Resolves a pointer string to an absolute file path on disk.
        Searches base_dir, workspace root, and CWD.
        """
        p = Path(pointer)
        if p.is_absolute() and p.exists() and p.is_file():
            return p

        # Check relative to base_dir (e.g. mock-data/fwa-mock/...)
        candidate1 = (self.base_dir / pointer).resolve()
        if candidate1.exists() and candidate1.is_file():
            return candidate1

        # Check relative to base_dir's parent (workspace root)
        candidate2 = (self.base_dir.parent / pointer).resolve()
        if candidate2.exists() and candidate2.is_file():
            return candidate2

        # Check relative to current working directory
        candidate3 = Path.cwd() / pointer
        if candidate3.exists() and candidate3.is_file():
            return candidate3.resolve()

        raise EvidenceNotFoundError(
            f"Evidence file could not be found for pointer: '{pointer}'. "
            f"Searched paths: [{candidate1}, {candidate2}, {candidate3}]"
        )

    def _load_json(self, pointer: str) -> Dict[str, Any]:
        """Loads and parses a JSON file from a pointer path."""
        target_path = self._resolve_path(pointer)
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as jde:
            raise EvidenceParseError(f"Malformed JSON in evidence file '{target_path}': {jde}") from jde
        except Exception as e:
            raise EvidenceLookupError(f"Failed to read evidence file '{target_path}': {e}") from e

    def _extract_pointer_value(self, pointers: Any, key: str) -> Optional[Any]:
        """Helper to extract a key from a dictionary, Pydantic model, or object."""
        if pointers is None:
            return None
        if isinstance(pointers, dict):
            return pointers.get(key)
        if hasattr(pointers, key):
            return getattr(pointers, key)
        if hasattr(pointers, "model_dump"):
            return pointers.model_dump().get(key)
        return None

    def resolve_clinical_evidence(
        self,
        pointers: Union[Dict[str, Any], BaseModel, Any],
    ) -> ClinicalEvidenceData:
        """
        Resolves the clinical evidence bundle (EHR progress notes, diagnoses, claim lines).
        """
        pointer = self._extract_pointer_value(pointers, "clinical_evidence")
        if not pointer:
            raise EvidenceNotFoundError("No 'clinical_evidence' pointer found in case evidence bundle.")

        raw_data = self._load_json(str(pointer))
        try:
            return ClinicalEvidenceData.model_validate(raw_data)
        except ValidationError as ve:
            raise EvidenceParseError(f"Schema validation failed for ClinicalEvidenceData ('{pointer}'): {ve}") from ve

    def resolve_risk_factors(
        self,
        pointers: Union[Dict[str, Any], BaseModel, Any],
    ) -> RiskFactorsData:
        """
        Resolves ML anomaly risk factors, feature attributions, and SHAP waterfall data.
        """
        pointer = self._extract_pointer_value(pointers, "risk_factors")
        if not pointer:
            raise EvidenceNotFoundError("No 'risk_factors' pointer found in case evidence bundle.")

        raw_data = self._load_json(str(pointer))
        try:
            return RiskFactorsData.model_validate(raw_data)
        except ValidationError as ve:
            raise EvidenceParseError(f"Schema validation failed for RiskFactorsData ('{pointer}'): {ve}") from ve

    def resolve_peer_comparison(
        self,
        pointers: Union[Dict[str, Any], BaseModel, Any],
    ) -> Optional[PeerComparisonDetailData]:
        """
        Resolves detailed peer comparison metrics, statistics, and distribution histogram.
        """
        peer_obj = self._extract_pointer_value(pointers, "peer_comparison")
        if not peer_obj:
            return None

        # Determine fixture file path from fixture_ref or direct string
        fixture_ref: Optional[str] = None
        if isinstance(peer_obj, str):
            fixture_ref = peer_obj
        elif isinstance(peer_obj, dict):
            fixture_ref = peer_obj.get("fixture_ref")
        elif hasattr(peer_obj, "fixture_ref"):
            fixture_ref = getattr(peer_obj, "fixture_ref", None)

        if not fixture_ref:
            # If no detailed fixture_ref is specified, construct model from embedded fields if present
            if isinstance(peer_obj, dict) and "specialty" in peer_obj:
                return PeerComparisonDetailData.model_validate(
                    {
                        "case_id": peer_obj.get("case_id", "UNKNOWN"),
                        "specialty": peer_obj.get("specialty", ""),
                        "region": peer_obj.get("region", ""),
                        "metric_name": peer_obj.get("metric_name", "Utilization Rate"),
                        "provider_value": peer_obj.get("provider_metric_value", 0.0),
                        "cohort_size": peer_obj.get("cohort_size", 1),
                    }
                )
            return None

        raw_data = self._load_json(fixture_ref)
        try:
            return PeerComparisonDetailData.model_validate(raw_data)
        except ValidationError as ve:
            raise EvidenceParseError(f"Schema validation failed for PeerComparisonDetailData ('{fixture_ref}'): {ve}") from ve

    def resolve_claim_flags(
        self,
        pointers: Union[Dict[str, Any], BaseModel, Any],
    ) -> Optional[ClaimFlagsData]:
        """
        Resolves clinical edit rule violations and policy citation flags.
        """
        pointer = self._extract_pointer_value(pointers, "claim_flags")
        if not pointer:
            return None

        raw_data = self._load_json(str(pointer))
        try:
            return ClaimFlagsData.model_validate(raw_data)
        except ValidationError as ve:
            raise EvidenceParseError(f"Schema validation failed for ClaimFlagsData ('{pointer}'): {ve}") from ve

    def resolve_drg_validation(
        self,
        pointers: Union[Dict[str, Any], BaseModel, Any],
    ) -> Optional[DRGValidationData]:
        """
        Resolves DRG validation analysis (for inpatient claims).
        """
        pointer = self._extract_pointer_value(pointers, "drg_validation")
        if not pointer:
            return None

        raw_data = self._load_json(str(pointer))
        try:
            return DRGValidationData.model_validate(raw_data)
        except ValidationError as ve:
            raise EvidenceParseError(f"Schema validation failed for DRGValidationData ('{pointer}'): {ve}") from ve

    def resolve_all(
        self,
        pointers: Union[Dict[str, Any], BaseModel, Any],
        case_id: Optional[str] = None,
        claim_ref: Optional[str] = None,
    ) -> FullEvidenceBundle:
        """
        Resolves all available evidence sub-bundles into a single aggregate FullEvidenceBundle.
        """
        clinical = None
        try:
            clinical = self.resolve_clinical_evidence(pointers)
        except EvidenceLookupError:
            pass

        risk = None
        try:
            risk = self.resolve_risk_factors(pointers)
        except EvidenceLookupError:
            pass

        peer = None
        try:
            peer = self.resolve_peer_comparison(pointers)
        except EvidenceLookupError:
            pass

        flags = None
        try:
            flags = self.resolve_claim_flags(pointers)
        except EvidenceLookupError:
            pass

        drg = None
        try:
            drg = self.resolve_drg_validation(pointers)
        except EvidenceLookupError:
            pass

        cid = case_id or (clinical.case_id if clinical else (risk.case_id if risk else "UNKNOWN"))
        cref = claim_ref or (clinical.claim_ref if clinical else (risk.claim_ref if risk else "UNKNOWN"))

        return FullEvidenceBundle(
            case_id=cid,
            claim_ref=cref,
            clinical_evidence=clinical,
            risk_factors=risk,
            peer_comparison_detail=peer,
            claim_flags=flags,
            drg_validation=drg,
        )
