"""Fleet Console UI server — a SEPARATE vendor-side deployable (ADR 0009 §4, #377).

This is the operator-facing console: it mounts the fleet API (``create_fleet_api``,
the operator read/issue/renew/revoke surface) AND serves the static SPA in this
directory. It is a DISTINCT deployable from:

  - ``fleet_console.intake`` — the internet-facing telemetry INTAKE (deployment→vendor
    push). Different trust zone; do not co-host on the public intake.
  - isA_Admin — the per-deployment business-data UI (ADR 0008). This console is its
    inverse (broad metadata across all customers), NEVER under any ``/admin`` path,
    NEVER reaching a customer DB (ADR 0009 §5).

Run (vendor-internal, behind VPN/SSO in real ops):

    export FLEET_DATABASE_URL="postgresql+psycopg://.../fleet"
    # Dev/test only — pin a signing key; in prod the operator pastes it per request:
    export FLEET_SIGNING_KEY_FILE="/path/to/offline-ed25519.pem"   # optional
    PYTHONPATH="$PWD/isA_common:$PWD/fleet" \
        uvicorn console_ui.server:app --port 8077    # (or: python fleet/console-ui/server.py)

The signing key is NOT stored hot by default: leave ``FLEET_SIGNING_KEY_FILE`` unset
and the operator supplies the offline key in each issue/renew request (ADR 0009 §2).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fleet_console import Base, create_fleet_api

UI_DIR = Path(__file__).resolve().parent


def _engine():
    url = os.environ.get("FLEET_DATABASE_URL", "sqlite:///fleet_console.db")
    eng = create_engine(url)
    # For a fresh DB / sqlite dev runs, ensure the schema exists. In prod the SQL
    # migrations (fleet/migrations/*.sql) own the schema; this is a no-op then.
    Base.metadata.create_all(eng)
    return eng


def _signing_key() -> Optional[bytes]:
    path = os.environ.get("FLEET_SIGNING_KEY_FILE")
    if not path:
        return None  # operator supplies the offline key per request (ADR 0009 §2)
    return Path(path).read_bytes()


def build_app(session_factory=None, signing_key_pem: Optional[bytes] = None) -> FastAPI:
    """Build the console app: the fleet API + the static SPA. Separate deployable."""
    if session_factory is None:
        session_factory = sessionmaker(bind=_engine(), class_=Session)
    if signing_key_pem is None:
        signing_key_pem = _signing_key()

    # The fleet API IS the app (gives us /fleet/* + /healthz); we then mount the UI.
    app = create_fleet_api(session_factory, signing_key_pem=signing_key_pem)
    app.title = "Fleet Console (UI + API)"
    # Serve the SPA at / (index.html, app.js, app.css). html=True -> / serves index.
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="console-ui")
    return app


app = build_app()


if __name__ == "__main__":  # pragma: no cover - manual run
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8077")))
