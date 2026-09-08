"""
Main entry point for Case Management Service.
Provides the FastAPI application, CORS middleware, health check endpoints,
and routes for audit case lifecycle management.
"""

from contextlib import asynccontextmanager
from typing import Dict, Any
from pathlib import Path
import yaml
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.config import settings
from src.database import get_db, engine, Base
from src.routes import router as cases_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager for startup and shutdown events.
    """
    # Verify or initialize DB connection on startup
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        # In testing or isolated offline modes, log warning without crashing
        print(f"Warning: Database connection check failed on startup: {e}")
    yield


app = FastAPI(
    title="WCT Case Management Service",
    description=(
        "Central System of Record for WCT Module 5 (Audit & Compliance Workflow). "
        "Manages healthcare audit case lifecycles, clinical evidence pointers, "
        "72-hour human-confirmation SLA clocks, and human auditor decisions."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Configuration for frontend auditor workbench
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Case Management API Routes
app.include_router(cases_router)


@app.get(
    "/",
    tags=["System"],
    summary="Service Information",
    response_model=Dict[str, Any],
)
def root_info() -> Dict[str, Any]:
    """Returns basic service identification and API status."""
    return {
        "service": settings.SERVICE_NAME,
        "version": "0.1.0",
        "status": "online",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
    }


@app.get(
    "/health",
    tags=["System"],
    summary="Health and Readiness Check",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
)
def health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Liveness and database readiness check for container orchestration and monitoring.
    """
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "service": settings.SERVICE_NAME,
        "database": db_status,
    }


def export_openapi_yaml(output_path: str = "openapi.yaml") -> None:
    """Exports current FastAPI OpenAPI JSON schema to a YAML specification file."""
    openapi_schema = app.openapi()
    target_file = Path(output_path)
    with open(target_file, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, sort_keys=False, default_flow_style=False)
    print(f"OpenAPI YAML successfully exported to {target_file.resolve()}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.SERVICE_PORT,
        reload=settings.DEBUG,
    )
