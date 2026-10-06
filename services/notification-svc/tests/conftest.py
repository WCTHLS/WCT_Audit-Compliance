"""
Pytest configuration and fixtures for notification-svc test suite.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.repository import repository


@pytest.fixture(autouse=True)
def clean_repository():
    """Ensure in-memory history is cleared before each test."""
    repository.clear()
    yield
    repository.clear()


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)
