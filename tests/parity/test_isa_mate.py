"""Parity smoke for the **isa-mate** service (the desktop/gateway agent).

Auth model (from isa_mate/gateway/server.py): only `GET /health` is public.
Every functional endpoint resolves identity through `_resolve_auth` /
`_resolve_auth_read` (Bearer JWT or api_key header), so the listing, chat,
query, teams, and autonomous-job flows are all auth-gated. The `auth_headers`
fixture supplies a real bootstrapped token and auto-skips when auth is
unavailable.

Identity note: handlers derive `user_id` from the auth context (the JWT),
NOT from request params — so we never pass a fake user id; we only pass the
bearer token. The autonomous background-job flow keys reads/cancels on the
returned `job_id`, so we register cleanup the moment a create may have
succeeded (DELETE = cancel) to stay prod-safe.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth/streaming nuances make those
brittle. `/v1/chat` returns an SSE stream; we still only check it does not 5xx.

Endpoints exercised (from isa_mate/gateway/server.py + execution routers):
  - GET    /health                                       (public liveness)
  - GET    /v1/skills                                    (list skills, auth-read)
  - GET    /v1/tools                                     (list tools, auth-read)
  - GET    /v1/teams                                     (list delegation teams, auth-read)
  - POST   /v1/query   {prompt}                          (one-shot query, auth)
  - POST   /v1/chat    {prompt}                          (chat / SSE, auth)
  - GET    /v1/autonomous/background-jobs                (list jobs, auth)
  - POST   /v1/autonomous/background-jobs {prompt,...}   (enqueue job, auth -> cleanup)
  - GET    /v1/autonomous/background-jobs/{job_id}       (read back, auth)
  - DELETE /v1/autonomous/background-jobs/{job_id}       (cancel, auth -> cleanup)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "isa-mate"


def test_isa_mate_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_isa_mate_list_skills(auth_headers):
    """List the skills collection — auth-gated read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/v1/skills", headers=auth_headers)
    assert r.status < 500, f"list skills 5xx: {r.text[:160]}"


def test_isa_mate_list_tools(auth_headers):
    """List the tools collection — auth-gated read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/v1/tools", headers=auth_headers)
    assert r.status < 500, f"list tools 5xx: {r.text[:160]}"


def test_isa_mate_list_teams(auth_headers):
    """List delegation teams — touches the delegation health-check path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/v1/teams", headers=auth_headers)
    assert r.status < 500, f"list teams 5xx: {r.text[:160]}"


def test_isa_mate_list_background_jobs(auth_headers):
    """List the autonomous background-jobs collection — auth-gated; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/v1/autonomous/background-jobs?limit=10", headers=auth_headers)
    assert r.status < 500, f"list background-jobs 5xx: {r.text[:160]}"


def test_isa_mate_query(auth_headers):
    """One-shot query flow — exercises the agent runtime; no 5xx expected.

    QueryRequest requires only `prompt`. Stateless, so no cleanup needed.
    """
    c = Client(SERVICE)
    payload = {"prompt": "parity-smoke: what is 2+2?"}
    r = c.post("/v1/query", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"query 5xx: {r.text[:160]}"


def test_isa_mate_chat(auth_headers):
    """Chat flow (SSE) — exercises the streaming agent path; no 5xx expected.

    ChatRequest requires only `prompt`. The response is a stream, but for parity
    we only need the request to resolve without a 5xx.
    """
    c = Client(SERVICE)
    payload = {"prompt": "parity-smoke: hello"}
    r = c.post("/v1/chat", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"chat 5xx: {r.text[:160]}"


def test_isa_mate_background_job_create_read_delete(auth_headers, cleanup):
    """CRUD parity: enqueue background job -> read back -> auto-cancel on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE
    (cancel) the moment the resource may have been created (keyed on the returned
    job_id), then read it back. Only parity-level assertions: every call < 500.

    Required field (from BackgroundJobInput): `prompt`. We send a clearly-fake
    test prompt and an idempotency_key so re-runs are de-duplicated rather than
    piling up jobs.
    """
    c = Client(SERVICE)
    payload = {
        "prompt": "parity-smoke background job",
        "idempotency_key": "parity-smoke-bgjob",
        "metadata": {"source": "parity-smoke"},
    }

    r = c.post(
        "/v1/autonomous/background-jobs",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"create background-job 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded — resolve the real
    # job_id from the response so teardown cancels the right resource. The
    # idempotency 409 path also returns a job_id, so cover that too.
    job_id = None
    body = r.json() if isinstance(r.json(), dict) else {}
    if body:
        job_id = body.get("id") or body.get("job_id")
        detail = body.get("detail")
        if job_id is None and isinstance(detail, dict):
            job_id = detail.get("job_id")
    if job_id is not None:
        cleanup(c, f"/v1/autonomous/background-jobs/{job_id}")

    # Read the resource back by id — still parity-level (no 5xx). Fall back to a
    # representative id when the create did not return one (still a valid path).
    lookup_id = job_id if job_id is not None else "parity-smoke-missing"
    r2 = c.get(
        f"/v1/autonomous/background-jobs/{lookup_id}",
        headers=auth_headers,
    )
    assert r2.status < 500, f"get background-job 5xx: {r2.text[:160]}"
