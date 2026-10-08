"""
Pytest configuration and fixtures for Provider Portal Service tests.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.repository import repository


@pytest.fixture(autouse=True)
def clean_repository():
    """Ensures repository is empty before and after each test."""
    repository.clear()
    yield
    repository.clear()


@pytest.fixture
async def client():
    """Provides async HTTP client configured for FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
