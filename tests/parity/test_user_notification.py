"""Parity smoke for the **user-notification** service (notification_service).

Public service: per the SN-PARITY-AUDIT (auth_required=False) and
microservices/notification_service/main.py, none of the `/api/v1/notifications/*`
handlers declare an auth dependency. So these tests intentionally send NO bearer
token — the endpoints are reachable without one.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth nuances make those brittle.

Endpoints exercised (from microservices/notification_service/main.py):
  - GET    /health                                          (public liveness)
  - GET    /api/v1/notifications?limit=&offset=             (list notifications)
  - GET    /api/v1/notifications/templates?limit=&offset=   (list templates)
  - GET    /api/v1/notifications/stats?period=all_time      (statistics view)
  - GET    /api/v1/notifications/in-app/{user_id}           (in-app list)
  - GET    /api/v1/notifications/in-app/{user_id}/unread-count
  - POST   /api/v1/notifications/templates                  (create template)
        body: CreateTemplateRequest{name, type, content} required
        (subject optional) -> response TemplateResponse.template.template_id
  - GET    /api/v1/notifications/templates/{template_id}    (read back)
  - DELETE /api/v1/notifications/templates/{template_id}    (delete -> cleanup)
  - POST   /api/v1/notifications/send                       (send notification)
        body: SendNotificationRequest{type, ...} -> response wraps
        notification.notification_id
  - GET    /api/v1/notifications/{notification_id}          (read back)
  - DELETE /api/v1/notifications/{notification_id}          (delete -> cleanup)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-notification"

# Clearly-fake parity test identity (not a real user).
TEST_USER = "usr_parity_smoke"


def test_user_notification_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_notification_list():
    """List the main notifications collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/notifications?limit=10&offset=0")
    assert r.status < 500, f"list notifications 5xx: {r.text[:160]}"


def test_user_notification_list_templates():
    """List notification templates — exercises the template read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/notifications/templates?limit=10&offset=0")
    assert r.status < 500, f"list templates 5xx: {r.text[:160]}"


def test_user_notification_stats():
    """Statistics view — touches the aggregation code path; no 5xx expected."""
    c = Client(SERVICE)
    r = c.get("/api/v1/notifications/stats?period=all_time")
    assert r.status < 500, f"stats 5xx: {r.text[:160]}"


def test_user_notification_in_app_list():
    """In-app notification list for a user — auth-free read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/notifications/in-app/{TEST_USER}?limit=10&offset=0")
    assert r.status < 500, f"in-app list 5xx: {r.text[:160]}"


def test_user_notification_unread_count():
    """Unread-count read — exercises the in-app aggregation path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/notifications/in-app/{TEST_USER}/unread-count")
    assert r.status < 500, f"unread-count 5xx: {r.text[:160]}"


def test_user_notification_template_crud(cleanup):
    """CRUD parity: create template -> read back -> auto-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the resource may have been created (keyed on the returned
    template_id), then read it back. Only parity-level assertions: < 500.

    Required fields (from CreateTemplateRequest): name, type, content.
    Response is TemplateResponse -> {"template": {"template_id": ...}}.
    """
    c = Client(SERVICE)
    payload = {
        "name": "parity-smoke",
        "description": "parity smoke test template",
        "type": "email",
        "subject": "parity-smoke subject",
        "content": "Hello {{name}}, this is a parity smoke template.",
        "variables": ["name"],
    }

    r = c.post("/api/v1/notifications/templates", json_body=payload)
    assert r.status < 500, f"create template 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded — resolve the real
    # template_id from the (possibly wrapped) response so teardown deletes it.
    template_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        tpl = body.get("template") if isinstance(body.get("template"), dict) else body
        template_id = tpl.get("template_id") or tpl.get("id")
        if template_id is not None:
            cleanup(c, f"/api/v1/notifications/templates/{template_id}")

    # Read the resource back by id — still parity-level (no 5xx). Fall back to a
    # representative id when the create did not return one (still a valid path).
    lookup_id = template_id if template_id is not None else "parity-smoke-missing"
    r2 = c.get(f"/api/v1/notifications/templates/{lookup_id}")
    assert r2.status < 500, f"get template 5xx: {r2.text[:160]}"


def test_user_notification_send_crud(cleanup):
    """CRUD parity: send an in-app notification -> read back -> auto-delete.

    Uses the in-app type so no external email provider (Resend) is required.
    Self-cleaning: registers the DELETE keyed on the returned notification_id
    the moment the create may have succeeded. Only parity-level asserts (< 500).

    SendNotificationRequest requires `type`; recipient/content are optional in
    the model, so we supply a minimal-but-realistic in-app payload.
    """
    c = Client(SERVICE)
    payload = {
        "type": "in_app",
        "recipient_id": TEST_USER,
        "subject": "parity-smoke",
        "content": "parity smoke in-app notification",
        "priority": "normal",
    }

    r = c.post("/api/v1/notifications/send", json_body=payload)
    assert r.status < 500, f"send notification 5xx: {r.text[:160]}"

    notification_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        note = (
            body.get("notification")
            if isinstance(body.get("notification"), dict)
            else body
        )
        notification_id = note.get("notification_id") or note.get("id")
        if notification_id is not None:
            cleanup(c, f"/api/v1/notifications/{notification_id}")

    lookup_id = (
        notification_id if notification_id is not None else "parity-smoke-missing"
    )
    r2 = c.get(f"/api/v1/notifications/{lookup_id}")
    assert r2.status < 500, f"get notification 5xx: {r2.text[:160]}"
