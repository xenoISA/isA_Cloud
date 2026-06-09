"""Parity smoke for the **user-wallet** service (wallet_service).

Public endpoints: the actual route handlers in
microservices/wallet_service/main.py carry NO auth dependency — every handler
takes only `Depends(get_wallet_service)`, so each endpoint is reachable without
a bearer token. The routes_registry `auth_required` flags are not wired to a
real dependency, and the SN-PARITY-AUDIT lists this service as
`auth_required=False`. So we exercise everything unauthenticated.

Parity signal = no 5xx + inter-service calls (account_client, postgres, NATS
event publishers) resolve. We deliberately assert ONLY `r.status < 500`
(400/401/403/404/422 are all acceptable parity outcomes), never specific bodies
or 200s — payload/auth nuances make those brittle. The bug we hunt is a 5xx.

Self-cleaning note: the wallet service exposes NO DELETE route for wallets (see
routes_registry.py — only GET/POST methods exist; there is no
`DELETE /api/v1/wallets/{wallet_id}`). So a created wallet cannot be torn down
over HTTP. We therefore keep create payloads clearly-fake (user_id starting
"parity-smoke-...") and rely on test isolation rather than registering a DELETE
that would itself 404/405. No id-bearing cleanup is registered for wallets.

Endpoints exercised (from microservices/wallet_service/main.py):
  - GET  /health                                          (public liveness)
  - GET  /api/v1/wallet/health                            (api-v1 health alias)
  - GET  /api/v1/wallet/stats                             (service statistics)
  - GET  /api/v1/wallets?user_id=...                      (list user wallets)
  - GET  /api/v1/wallets/credits/balance?user_id=...      (credit balance compat)
  - GET  /api/v1/wallets/transactions?user_id=...         (user txn history)
  - GET  /api/v1/wallets/statistics?user_id=...           (user wallet stats)
  - POST /api/v1/wallets                                  (create wallet)
        body: WalletCreate{user_id, wallet_type, initial_balance, currency}
  - GET  /api/v1/wallets/{wallet_id}                      (read back by id)
  - GET  /api/v1/wallets/{wallet_id}/balance             (wallet balance)
  - POST /api/v1/wallets/{wallet_id}/deposit             (deposit funds)
        body: DepositRequest{amount, description}
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-wallet"

# Clearly-fake parity test user — safe to create against prod.
TEST_USER = "parity-smoke-user"


def test_user_wallet_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_wallet_api_health():
    """API-v1 health alias — exercises the same handler path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/wallet/health")
    assert r.status < 500, f"/api/v1/wallet/health 5xx: {r.text[:160]}"


def test_user_wallet_stats():
    """Service statistics endpoint — exercises a DB-backed read; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/wallet/stats")
    assert r.status < 500, f"stats 5xx: {r.text[:160]}"


def test_user_wallet_list_wallets():
    """List the main wallets collection for a user — must resolve without a 5xx.

    user_id is a required query param (Query(...)); omitting it yields 422,
    which is still < 500.
    """
    c = Client(SERVICE)
    r = c.get(f"/api/v1/wallets?user_id={TEST_USER}")
    assert r.status < 500, f"list wallets 5xx: {r.text[:160]}"


def test_user_wallet_credit_balance():
    """Backward-compat credit balance read — exercises get_user_wallets + the
    auto-create-default-wallet branch. Must not 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/wallets/credits/balance?user_id={TEST_USER}")
    assert r.status < 500, f"credit balance 5xx: {r.text[:160]}"


def test_user_wallet_user_transactions():
    """User transaction history across all wallets — read path, must not 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/wallets/transactions?user_id={TEST_USER}")
    assert r.status < 500, f"user transactions 5xx: {r.text[:160]}"


def test_user_wallet_user_statistics():
    """Aggregated user wallet statistics — exercises the stats aggregation path.

    No 5xx expected even when the user has no wallets.
    """
    c = Client(SERVICE)
    r = c.get(f"/api/v1/wallets/statistics?user_id={TEST_USER}")
    assert r.status < 500, f"user statistics 5xx: {r.text[:160]}"


def test_user_wallet_create_read_deposit(cleanup):
    """CRUD-ish parity: create wallet -> read back by id -> balance -> deposit.

    There is no DELETE route for wallets (routes_registry exposes only GET/POST),
    so we cannot auto-clean over HTTP; we keep the payload clearly-fake and rely
    on test isolation. Only parity-level assertions: every call < 500.

    Required fields derived from WalletCreate: user_id (required); wallet_type,
    initial_balance, currency all have defaults but we send valid values
    explicitly. DepositRequest requires a positive `amount`.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER,
        "wallet_type": "fiat",
        "initial_balance": "0.00",
        "currency": "CREDIT",
        "metadata": {"source": "parity-smoke"},
    }

    r = c.post("/api/v1/wallets", json_body=payload)
    assert r.status < 500, f"create wallet 5xx: {r.text[:160]}"

    # Resolve the real wallet_id from WalletResponse if the create succeeded.
    wallet_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        wallet_id = body.get("wallet_id")

    # Read the resource back by id — still parity-level (no 5xx).
    if wallet_id:
        r2 = c.get(f"/api/v1/wallets/{wallet_id}")
        assert r2.status < 500, f"get wallet 5xx: {r2.text[:160]}"

        r3 = c.get(f"/api/v1/wallets/{wallet_id}/balance")
        assert r3.status < 500, f"wallet balance 5xx: {r3.text[:160]}"

        # Deposit a small amount — exercises the write + event-publish path.
        deposit = {"amount": "10.00", "description": "parity-smoke deposit"}
        r4 = c.post(f"/api/v1/wallets/{wallet_id}/deposit", json_body=deposit)
        assert r4.status < 500, f"deposit 5xx: {r4.text[:160]}"
