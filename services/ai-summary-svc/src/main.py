"""
Main entry point for AI Summary Service.
Provides the FastAPI application, CORS middleware, healthcheck,
and clinical summarization endpoints for WCT Module 5.
"""

from typing import Any, Dict
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from app.summarizer import (
    SummarizeRequest,
    SummarizeResponse,
    summarizer_engine,
)
from llm_client import llm_client

app = FastAPI(
    title="WCT AI Summary Service",
    description=(
        "AI-Powered Clinical Summary & Risk Explanation Service for WCT Module 5 "
        "(Audit & Compliance Workflow). Synthesizes EHR chart excerpts, SHAP explainability, "
        "and deterministic peer comparison statistics for healthcare audit investigators."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
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
    summary="Health and LLM Readiness Check",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def health_check() -> Dict[str, Any]:
    """
    Liveness and LLM connectivity probe for container orchestration.
    """
    llm_health = await llm_client.check_health()
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "llm": llm_health,
    }


@app.post(
    "/summarize",
    tags=["Clinical Summarization"],
    summary="Generate AI Clinical Audit Summary",
    response_model=SummarizeResponse,
    status_code=status.HTTP_200_OK,
)
async def summarize_case_endpoint(request: SummarizeRequest) -> SummarizeResponse:
    """
    Generates a structured clinical audit summary, risk factor breakdown,
    and peer comparison narrative from case evidence pointers.
    """
    return await summarizer_engine.summarize_case(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.SERVICE_PORT,
        reload=settings.DEBUG,
    )
