"""
Billing pipeline smoke test fixtures.

Provides service availability checks and shared HTTP clients for
cross-service smoke tests against the billing pipeline.
"""

import os
import socket

import pytest
import httpx


# ---------------------------------------------------------------------------
# Service URLs (override via env vars)
# ---------------------------------------------------------------------------

MODEL_SERVICE_URL = os.environ.get("MODEL_SERVICE_URL", "http://localhost:8082")
BILLING_SERVICE_URL = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8216")
SUBSCRIPTION_SERVICE_URL = os.environ.get("SUBSCRIPTION_SERVICE_URL", "http://localhost:8228")
NATS_HOST = os.environ.get("NATS_HOST", "localhost")
NATS_PORT = int(os.environ.get("NATS_PORT", "4222"))

# Test user — must have an active subscription with credits
SMOKE_USER_ID = os.environ.get("SMOKE_USER_ID", "smoke-test-user")
SMOKE_ORG_ID = os.environ.get("SMOKE_ORG_ID", "")
# User known to have zero credits (for 402 test)
SMOKE_BROKE_USER_ID = os.environ.get("SMOKE_BROKE_USER_ID", "smoke-test-broke-user")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


async def _service_healthy(url: str, path: str = "/health") -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}{path}")
            return resp.status_code < 500
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: Cross-service smoke tests")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def model_service_url():
    return MODEL_SERVICE_URL


@pytest.fixture(scope="session")
def billing_service_url():
    return BILLING_SERVICE_URL


@pytest.fixture(scope="session")
def subscription_service_url():
    return SUBSCRIPTION_SERVICE_URL


@pytest.fixture(scope="session")
def smoke_user_id():
    return SMOKE_USER_ID


@pytest.fixture(scope="session")
def smoke_org_id():
    return SMOKE_ORG_ID


@pytest.fixture(scope="session")
def smoke_broke_user_id():
    return SMOKE_BROKE_USER_ID


@pytest.fixture(scope="session")
def nats_config():
    return {"host": NATS_HOST, "port": NATS_PORT}


# ---------------------------------------------------------------------------
# Service availability gates (skip entire suite if services are down)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
async def require_billing_services():
    """Skip all smoke tests if core billing services are not reachable."""
    errors = []

    if not await _service_healthy(MODEL_SERVICE_URL):
        errors.append(f"isA_Model ({MODEL_SERVICE_URL})")
    if not await _service_healthy(BILLING_SERVICE_URL):
        errors.append(f"billing_service ({BILLING_SERVICE_URL})")
    if not await _service_healthy(SUBSCRIPTION_SERVICE_URL):
        errors.append(f"subscription_service ({SUBSCRIPTION_SERVICE_URL})")
    if not _port_open(NATS_HOST, NATS_PORT):
        errors.append(f"NATS ({NATS_HOST}:{NATS_PORT})")

    if errors:
        pytest.skip(
            f"Billing pipeline services unavailable: {', '.join(errors)}. "
            "Set env vars (MODEL_SERVICE_URL, BILLING_SERVICE_URL, "
            "SUBSCRIPTION_SERVICE_URL, NATS_HOST) to configure."
        )
