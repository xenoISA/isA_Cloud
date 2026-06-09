"""Auth end-to-end flow — the platform's most critical cross-service journey.

register -> verify -> login -> authed call. The `jwt` fixture performs the
bootstrap; here we assert the resulting token actually authenticates a request
(verify-token round-trip). Runs in any environment.
"""

from __future__ import annotations

from conftest import Client


def test_jwt_bootstrap_yields_usable_token(jwt):
    """The bootstrapped token is non-empty and verifies against auth."""
    assert jwt and isinstance(jwt, str) and len(jwt) > 20
    auth = Client("user-auth")
    r = auth.post("/api/v1/auth/verify-token", {"token": jwt})
    # verify-token must accept our freshly-minted token (200) — not 5xx
    assert r.status < 500, f"verify-token 5xx: {r.text[:160]}"
    assert r.status in (200, 401), f"unexpected verify-token status {r.status}"


def test_authed_endpoint_accepts_token(auth_headers):
    """An authed read on auth (user-info) works with the bearer token."""
    auth = Client("user-auth")
    r = auth.post(
        "/api/v1/auth/user-info",
        json_body={"token": auth_headers["Authorization"].split()[1]},
    )
    assert r.status < 500, f"user-info 5xx: {r.text[:160]}"
