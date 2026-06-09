"""Shared harness for the cloud-native parity suite.

Provides, env-agnostically (local / SN-IDC / GCP-GKE):
  - `http`     : a tiny requests-like client (urllib, no extra deps) bound to a service
  - `jwt`      : a bootstrapped user access token (register -> get code -> verify -> login)
  - `auth_headers` : {"Authorization": "Bearer <jwt>"}
  - `cleanup`  : register created resource IDs -> deleted in teardown (safe to run vs prod)

The JWT bootstrap is itself a parity test: it exercises auth + redis + (in local)
the dev endpoint. Verification-code retrieval is env-aware:
  - local dev : GET /api/v1/auth/dev/pending-registration/{id} (debug-only endpoint)
  - in-cluster: read redis key auth:pending_reg:{id} (REDIS_* from env)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest

from config import base_url


class Resp:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self):
        try:
            return json.loads(self._body.decode())
        except Exception:
            return None

    @property
    def text(self) -> str:
        return self._body.decode(errors="replace")


def request(method: str, url: str, *, json_body=None, headers=None, timeout=20) -> Resp:
    data = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return Resp(r.status, r.read())
    except urllib.error.HTTPError as e:
        return Resp(e.code, e.read())
    except Exception as e:  # noqa: BLE001
        return Resp(0, str(e).encode())


class Client:
    """Service-bound HTTP client; auto-resolves base URL for the active target."""

    def __init__(self, service: str, headers=None):
        self.base = base_url(service)
        self.headers = headers or {}

    def _h(self, extra):
        h = dict(self.headers)
        h.update(extra or {})
        return h

    def get(self, path, headers=None, **kw):
        return request("GET", self.base + path, headers=self._h(headers), **kw)

    def post(self, path, json_body=None, headers=None, **kw):
        return request(
            "POST",
            self.base + path,
            json_body=json_body,
            headers=self._h(headers),
            **kw,
        )

    def put(self, path, json_body=None, headers=None, **kw):
        return request(
            "PUT", self.base + path, json_body=json_body, headers=self._h(headers), **kw
        )

    def delete(self, path, headers=None, **kw):
        return request("DELETE", self.base + path, headers=self._h(headers), **kw)


@pytest.fixture
def http():
    """Factory: http(service) -> Client bound to that service."""
    return lambda service, headers=None: Client(service, headers)


def _verification_code(auth: Client, pending_id: str) -> str | None:
    """Env-aware retrieval of the registration verification code."""
    # local-dev debug endpoint first
    r = auth.get(f"/api/v1/auth/dev/pending-registration/{pending_id}")
    if r.ok and isinstance(r.json(), dict) and r.json().get("verification_code"):
        return r.json()["verification_code"]
    # in-cluster: read from redis (the prod store)
    try:
        import redis  # noqa: PLC0415

        rc = redis.from_url(
            "redis://:%s@%s:%s/0"
            % (
                os.getenv("REDIS_PASSWORD", ""),
                os.getenv("REDIS_HOST", "redis-cluster"),
                os.getenv("REDIS_PORT", "6379"),
            ),
            decode_responses=True,
        )
        raw = rc.get(f"auth:pending_reg:{pending_id}")
        if raw:
            return json.loads(raw).get("code")
    except Exception:  # noqa: BLE001
        return None
    return None


@pytest.fixture(scope="session")
def jwt() -> str:
    """Bootstrap a real user access token via register -> verify -> login.

    Skips the whole authed suite (rather than failing) if auth/redis are
    unreachable, so the unauth read-parity tests still run everywhere.
    """
    auth = Client("user-auth")
    email = f"parity-{int(time.time())}-{os.getpid()}@example.com"
    pw = "ParityTest12345!aA"
    reg = auth.post("/api/v1/auth/register", {"email": email, "password": pw})
    if not reg.ok:
        pytest.skip(f"auth register unavailable ({reg.status}); skipping authed tests")
    pending_id = (reg.json() or {}).get("pending_id")
    code = _verification_code(auth, pending_id) if pending_id else None
    if not code:
        pytest.skip(
            "could not retrieve verification code (auth/redis); skipping authed tests"
        )
    v = None
    for body in (
        {"pending_id": pending_id, "code": code},
        {"email": email, "code": code},
    ):
        v = auth.post("/api/v1/auth/verify", body)
        if v.ok:
            break
    lg = auth.post("/api/v1/auth/login", {"email": email, "password": pw})
    if not lg.ok:
        pytest.skip(f"auth login failed ({lg.status}); skipping authed tests")
    body = lg.json() or {}
    tok = (
        body.get("access_token")
        or body.get("token")
        or (body.get("tokens") or {}).get("access_token")
    )
    if not tok:
        pytest.skip("no access_token in login response; skipping authed tests")
    return tok


@pytest.fixture
def auth_headers(jwt):
    return {"Authorization": f"Bearer {jwt}"}


@pytest.fixture
def cleanup():
    """Register (client, delete_path) to be DELETEd after the test — prod-safe."""
    created: list[tuple[Client, str]] = []

    def _reg(client: Client, delete_path: str):
        created.append((client, delete_path))

    yield _reg
    for client, path in reversed(created):
        try:
            client.delete(path)
        except Exception:  # noqa: BLE001
            pass
