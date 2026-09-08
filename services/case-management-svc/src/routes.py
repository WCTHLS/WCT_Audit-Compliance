"""
FastAPI route handlers for Case Management Service CRUD API.
Implements POST /cases, GET /cases, GET /cases/{case_id}, and PATCH /cases/{case_id}.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.schemas import CaseCreate, CaseRead, CaseUpdate, CaseListResponse
from src import crud
from event_contracts import CaseStatusEnum
from auth_middleware.dependencies import get_current_user
from auth_middleware.models import AuthenticatedUser

router = APIRouter(prefix="/cases", tags=["Case Management"])


@router.post(
    "",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Audit Case",
    description="Creates a new audit case record with 72-hour SLA deadline tracking and evidence pointers.",
)
def create_new_case(
    case_in: CaseCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CaseRead:
    """Creates a new case in the database."""
    existing = crud.get_case_by_id(db, case_in.case_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Case with ID '{case_in.case_id}' already exists.",
        )

    db_case = crud.create_case(db, case_in)
    return CaseRead.model_validate(db_case)


@router.get(
    "",
    response_model=CaseListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Audit Cases",
    description="Retrieves a paginated list of audit cases with optional filters for workbench queues.",
)
def get_cases(
    status_filter: Optional[CaseStatusEnum] = Query(None, alias="status", description="Filter by case status"),
    assigned_auditor: Optional[str] = Query(None, description="Filter by assigned auditor username/email"),
    source_module: Optional[str] = Query(None, description="Filter by source module (e.g. fwa_detection)"),
    sla_breached: Optional[bool] = Query(None, description="Filter by SLA breach status"),
    skip: int = Query(0, ge=0, description="Number of cases to skip (pagination offset)"),
    limit: int = Query(50, ge=1, le=100, description="Max cases to return (page size)"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CaseListResponse:
    """Lists audit cases matching criteria."""
    status_val = status_filter.value if status_filter else None
    items, total = crud.list_cases(
        db=db,
        status=status_val,
        assigned_auditor=assigned_auditor,
        source_module=source_module,
        sla_breached=sla_breached,
        skip=skip,
        limit=limit,
    )

    return CaseListResponse(
        items=[CaseRead.model_validate(c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{case_id}",
    response_model=CaseRead,
    status_code=status.HTTP_200_OK,
    summary="Get Case Details",
    description="Retrieves full case details including all clinical evidence pointers and audit history.",
)
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CaseRead:
    """Fetches a specific case by case_id."""
    db_case = crud.get_case_by_id(db, case_id)
    if not db_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found.",
        )
    return CaseRead.model_validate(db_case)


@router.patch(
    "/{case_id}",
    response_model=CaseRead,
    status_code=status.HTTP_200_OK,
    summary="Update Case",
    description="Applies partial updates to a case (assign auditor, transition status, or record human decision).",
)
def patch_case(
    case_id: str,
    case_in: CaseUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CaseRead:
    """Updates fields on an existing case."""
    db_case = crud.get_case_by_id(db, case_id)
    if not db_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found.",
        )

    # If decision is provided, ensure rationale is present either in request or existing record
    if case_in.decision is not None and not case_in.decision_rationale and not db_case.decision_rationale:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A non-empty 'decision_rationale' is mandatory when recording an auditor decision.",
        )

    # Auto-assign decided_by to the authenticated user if not explicitly given
    if case_in.decision is not None and not case_in.decided_by:
        case_in.decided_by = current_user.email or current_user.name or current_user.user_id

    updated_case = crud.update_case(db, db_case, case_in)
    return CaseRead.model_validate(updated_case)
