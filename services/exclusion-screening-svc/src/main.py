"""
Main entry point for Exclusion Screening Service.
Provides FastAPI endpoints for screening provider entities against OIG LEIE exclusions.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.config import settings
from src.db import get_db, engine, Base
from src.schemas import ScreenRequest, ScreenResponse, HealthResponse
from src.service import screen_case, get_health_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager: ensures table creation on startup.
    """
    try:
        # Create tables if they do not exist
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Warning: Database initialization failed or running offline: {e}")
    yield


app = FastAPI(
    title="WCT Exclusion Screening Service",
    description=(
        "Microservice for WCT Module 5 (Audit & Compliance). "
        "Screens case provider entities, billing facilities, and fraud ring networks "
        "against the OIG LEIE and federal exclusion databases."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """
    Returns service health, dataset snapshot date, and record counts.
    """
    try:
        return get_health_status(db)
    except Exception as e:
        return HealthResponse(
            status="degraded",
            service=settings.SERVICE_NAME,
            record_counts={},
            snapshot_info={"error": str(e)},
            timestamp="",
        )


@app.post("/screen", response_model=ScreenResponse, tags=["Exclusion Screening"])
def screen_case_endpoint(payload: ScreenRequest, db: Session = Depends(get_db)):
    """
    Screens all providers, facilities, and fraud-ring entities related to a case.
    Returns MATCH, POSSIBLE_MATCH, or NO_MATCH per entity and an aggregate result.
    """
    try:
        return screen_case(db=db, req=payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Exclusion screening failed: {str(e)}",
        )
