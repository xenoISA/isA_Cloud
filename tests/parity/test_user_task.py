"""Parity smoke for the **user-task** service (task_service).

Auth-gated: per microservices/task_service/routes_registry.py, every functional
`/api/v1/tasks*`, `/api/v1/analytics`, etc. endpoint is `auth_required=True`
(only `/health`, `/health/detailed`, `/api/v1/tasks/health` are public). The
`auth_headers` fixture supplies a real bootstrapped token and auto-skips when
auth is unavailable.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth nuances make those brittle.

Endpoints exercised (from routes_registry.py + task_service.py):
  - GET  /health                                   (public liveness)
  - GET  /api/v1/tasks?limit=10&offset=0           (list, auth)
  - POST /api/v1/tasks                             (create, auth)
        body: TaskCreateRequest{name, task_type, ...} — name + task_type required
  - GET  /api/v1/tasks/{task_id}                   (read back, auth)
  - DELETE /api/v1/tasks/{task_id}                 (soft-delete, auth -> cleanup)
  - POST /api/v1/tasks/{task_id}/execute           (execute, auth)
        body: TaskExecutionRequest{trigger_type, trigger_data}
  - GET  /api/v1/tasks/{task_id}/executions        (execution history, auth)
  - GET  /api/v1/analytics?days=30                 (analytics, auth)

The create handler returns the new task keyed on `task_id` (string), so we
register cleanup the moment a create may have succeeded.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-task"


def test_user_task_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_task_list(auth_headers):
    """List the main tasks collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/tasks?limit=10&offset=0", headers=auth_headers)
    assert r.status < 500, f"list tasks 5xx: {r.text[:160]}"


def test_user_task_analytics(auth_headers):
    """Analytics view — exercises the auth-gated aggregation path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/analytics?days=30", headers=auth_headers)
    assert r.status < 500, f"analytics 5xx: {r.text[:160]}"


def _extract_task_id(resp):
    """Resolve the created task's id from a create response, if present."""
    if not resp.ok:
        return None
    body = resp.json() if isinstance(resp.json(), dict) else {}
    # Handler returns the task keyed on task_id; fall back to common variants.
    return (
        body.get("task_id") or body.get("id") or (body.get("task") or {}).get("task_id")
    )


def test_user_task_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create task -> read back -> auto-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the resource may have been created (keyed on the returned task_id),
    then read it back. Only parity-level assertions: every call must be < 500.

    Required fields (from TaskCreateRequest): name, task_type. We send a clearly
    -fake task with a minimal valid TaskType ("todo").
    """
    c = Client(SERVICE)
    payload = {
        "name": "parity-smoke",
        "description": "parity smoke test task",
        "task_type": "todo",
        "priority": "medium",
    }

    r = c.post("/api/v1/tasks", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create task 5xx: {r.text[:160]}"

    task_id = _extract_task_id(r)
    if task_id is not None:
        cleanup(c, f"/api/v1/tasks/{task_id}")

    # Read the resource back by id — still parity-level (no 5xx). Fall back to a
    # representative id when the create did not return one (still valid path).
    lookup_id = task_id if task_id is not None else "parity-smoke-missing"
    r2 = c.get(f"/api/v1/tasks/{lookup_id}", headers=auth_headers)
    assert r2.status < 500, f"get task 5xx: {r2.text[:160]}"


def test_user_task_execute_and_executions(auth_headers, cleanup):
    """Execution parity: create -> execute -> read execution history; no 5xx.

    Exercises the task-execution code path (which fans out to other services).
    Self-cleaning: registers the task DELETE the moment a create may have
    succeeded. Parity-level assertions only.
    """
    c = Client(SERVICE)
    payload = {
        "name": "parity-smoke-exec",
        "description": "parity smoke execution task",
        "task_type": "todo",
        "priority": "low",
    }

    r = c.post("/api/v1/tasks", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create task 5xx: {r.text[:160]}"

    task_id = _extract_task_id(r)
    if task_id is not None:
        cleanup(c, f"/api/v1/tasks/{task_id}")

    exec_id = task_id if task_id is not None else "parity-smoke-missing"

    r2 = c.post(
        f"/api/v1/tasks/{exec_id}/execute",
        json_body={"trigger_type": "manual", "trigger_data": {}},
        headers=auth_headers,
    )
    assert r2.status < 500, f"execute task 5xx: {r2.text[:160]}"

    r3 = c.get(f"/api/v1/tasks/{exec_id}/executions", headers=auth_headers)
    assert r3.status < 500, f"get executions 5xx: {r3.text[:160]}"
