"""Parity smoke for the **user-training** service (training_service).

Mixed auth posture (from microservices/training_service/main.py + auth.py):
  - Public:    /health, /live, /api/v1/training/health, /api/v1/training/courses,
               /api/v1/training/courses/{id}, /api/v1/training/quizzes/{id},
               /api/v1/training/labs/{id},
               /api/v1/training/completion-proofs/{code}/verify,
               /api/v1/training/k12/contract
  - Auth-gated: every learner/learning action resolves identity via
               require_user_id() (Bearer token verified against the auth
               service, or gateway-injected user id). Enrollments, submissions,
               progress, quiz attempts, sandbox, completion proofs, admin/review
               all require auth (401/403 without it).

Parity signal = no 5xx + inter-service calls resolve. We assert ONLY
`r.status < 500` (401/403/404/422 are all acceptable parity outcomes), never
specific bodies or 200s — payload/auth/seed-data nuances make those brittle.

Note on cleanup: the training service exposes NO delete endpoint. Enrollment is
keyed per (user, course) and the create path is idempotent, so the create flows
below are inherently self-cleaning against a shared environment — they create no
unbounded resources. Flows mirror the SN-PARITY-AUDIT.md user-training section
(enrollment_flow, quiz_attempt_flow, health_check).
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-training"
BASE = "/api/v1/training"

# A clearly-fake but catalog-plausible course code used by the audit's flows.
SMOKE_COURSE = "F101"


def test_user_training_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_training_versioned_health():
    """Versioned health endpoint — public, must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(f"{BASE}/health")
    assert r.status < 500, f"versioned health 5xx: {r.text[:160]}"


def test_user_training_list_courses():
    """List the main catalog collection (public) — no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"{BASE}/courses")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"list courses 5xx: {r.text[:160]}"


def test_user_training_list_courses_filtered():
    """Catalog with an audience_line filter — exercises the query path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"{BASE}/courses?audience_line=developer")
    assert r.status < 500, f"filtered courses 5xx: {r.text[:160]}"


def test_user_training_k12_contract():
    """K12 contract endpoint (public) — exercises the static contract load; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"{BASE}/k12/contract")
    assert r.status < 500, f"k12 contract 5xx: {r.text[:160]}"


def _extract_course_id(resp):
    """Pull a usable course id from the catalog list response, if present."""
    if not resp.ok:
        return None
    body = resp.json()
    if not isinstance(body, dict):
        return None
    courses = body.get("courses") or body.get("items") or []
    if courses and isinstance(courses, list) and isinstance(courses[0], dict):
        return courses[0].get("id") or courses[0].get("courseId")
    return None


def test_user_training_get_course_by_id():
    """Read a single course by id (public). Uses a real id when discoverable,
    else a fake id — both are valid paths (404 is acceptable, only <500 matters).
    """
    c = Client(SERVICE)
    listing = c.get(f"{BASE}/courses")
    course_id = _extract_course_id(listing) or SMOKE_COURSE
    r = c.get(f"{BASE}/courses/{course_id}")
    assert r.status < 500, f"get course 5xx: {r.text[:160]}"


def test_user_training_progress(auth_headers):
    """Auth-gated learner progress view — exercises identity resolution; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"{BASE}/me/progress", headers=auth_headers)
    assert r.status < 500, f"progress 5xx: {r.text[:160]}"


def test_user_training_timeline(auth_headers):
    """Auth-gated learner timeline view — no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"{BASE}/me/timeline", headers=auth_headers)
    assert r.status < 500, f"timeline 5xx: {r.text[:160]}"


def _extract_enrollment_course(resp):
    """Resolve the course id echoed back by a successful enrollment, if present."""
    if not resp.ok:
        return None
    body = resp.json()
    if not isinstance(body, dict):
        return None
    return body.get("courseId") or body.get("course_id")


def test_user_training_enrollment_flow(auth_headers):
    """CRUD-style parity: enroll in a course -> read learner progress back.

    Mirrors the audit's enrollment_flow. Minimal valid payload per
    EnrollmentRequest is just {"courseId": <id>}. There is no DELETE endpoint;
    enrollment is idempotent per (user, course), so this is self-cleaning and
    safe to run repeatedly against a shared environment. Parity-level only.
    """
    c = Client(SERVICE)

    # Prefer a real catalog course so the create can actually resolve; fall back
    # to the audit's fake code (still a valid path -> 404, never a 5xx).
    course_id = _extract_course_id(c.get(f"{BASE}/courses")) or SMOKE_COURSE

    r = c.post(
        f"{BASE}/enrollments",
        json_body={"courseId": course_id},
        headers=auth_headers,
    )
    assert r.status < 500, f"enroll 5xx: {r.text[:160]}"

    # Read learner progress back — confirms the read path resolves post-create.
    r2 = c.get(f"{BASE}/me/progress", headers=auth_headers)
    assert r2.status < 500, f"progress after enroll 5xx: {r2.text[:160]}"


def test_user_training_submission_flow(auth_headers):
    """Submit lesson work -> read progress. Mirrors the audit's enrollment_flow
    tail. Required fields per SubmissionRequest: courseId, lessonId, content.
    Self-cleaning (no resource accretion that needs a DELETE). Parity-level only.
    """
    c = Client(SERVICE)
    course_id = _extract_course_id(c.get(f"{BASE}/courses")) or SMOKE_COURSE

    r = c.post(
        f"{BASE}/submissions",
        json_body={
            "courseId": course_id,
            "lessonId": f"{course_id}-L1",
            "content": "parity-smoke",
        },
        headers=auth_headers,
    )
    assert r.status < 500, f"submit work 5xx: {r.text[:160]}"

    r2 = c.get(f"{BASE}/me/progress", headers=auth_headers)
    assert r2.status < 500, f"progress after submit 5xx: {r2.text[:160]}"


def test_user_training_quiz_attempt_flow(auth_headers):
    """Quiz parity: read quiz def (public) -> create attempt (auth) -> submit
    answers (auth). Mirrors the audit's quiz_attempt_flow. We never assert the
    quiz exists; a missing quiz is a 404, not a 5xx. Parity-level only.
    """
    c = Client(SERVICE)
    quiz_id = "F101-QUIZ"

    r0 = c.get(f"{BASE}/quizzes/{quiz_id}")
    assert r0.status < 500, f"get quiz 5xx: {r0.text[:160]}"

    r1 = c.post(f"{BASE}/quizzes/{quiz_id}/attempts", headers=auth_headers)
    assert r1.status < 500, f"create attempt 5xx: {r1.text[:160]}"

    attempt_id = None
    if r1.ok:
        body = r1.json()
        if isinstance(body, dict):
            attempt_id = body.get("id") or body.get("attemptId")
    lookup = attempt_id if attempt_id is not None else "parity-smoke-missing"

    r2 = c.post(
        f"{BASE}/attempts/{lookup}/submit",
        json_body={"answers": [{"questionId": "q1", "selectedOption": "A"}]},
        headers=auth_headers,
    )
    assert r2.status < 500, f"submit attempt 5xx: {r2.text[:160]}"


def test_user_training_completion_eligibility(auth_headers):
    """Auth-gated completion eligibility check — exercises the aggregation path
    over learner state; no 5xx (404 for an unknown course is acceptable).
    """
    c = Client(SERVICE)
    course_id = _extract_course_id(c.get(f"{BASE}/courses")) or SMOKE_COURSE
    r = c.get(f"{BASE}/completion-eligibility/{course_id}", headers=auth_headers)
    assert r.status < 500, f"completion eligibility 5xx: {r.text[:160]}"


def test_user_training_completion_proof_verify():
    """Public completion-proof verification — a bogus code must resolve to a
    not_found-style response, never a 5xx.
    """
    c = Client(SERVICE)
    r = c.get(f"{BASE}/completion-proofs/parity-smoke-missing/verify")
    assert r.status < 500, f"verify proof 5xx: {r.text[:160]}"
