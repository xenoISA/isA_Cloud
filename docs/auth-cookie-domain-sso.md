# Auth Cookie Domain Configuration for Multi-Zone SSO

> Related: Issue #76 — Cross-zone SSO for Multi-Zone routing

## Problem

The isA platform serves multiple frontend zones through APISIX:
- `/` — Main app (isa-app)
- `/console` — Console UI (isa-console)
- `/docs` — Documentation (isa-docs)

For SSO to work across all zones, the JWT refresh token cookie must be set on the
**root domain** so that all zones can read it. Without this, a user who logs in on
`/` would not be authenticated when navigating to `/console`.

## Architecture

```
Browser
  |
  +-- GET /            -> APISIX -> isa-app:4100       (reads cookie)
  +-- GET /console     -> APISIX -> isa-console:4200   (reads cookie)
  +-- GET /docs        -> APISIX -> isa-docs:4300      (reads cookie)
  |
  +-- POST /api/v1/auth/login    -> APISIX -> auth_service   (sets cookie)
  +-- POST /api/v1/auth/refresh  -> APISIX -> auth_service   (sets cookie)
  +-- POST /api/v1/auth/verify   -> APISIX -> auth_service   (sets cookie)
```

## Implementation — Two Layers

### Layer 1: APISIX Gateway (isA_Cloud) — DONE

The consul-apisix-sync script creates high-priority (priority=30) overlay routes for
the three auth endpoints that issue tokens:

- `/api/v1/auth/login`
- `/api/v1/auth/refresh`
- `/api/v1/auth/verify`

These routes add a `response-rewrite` plugin that sets an `X-Auth-Cookie-Domain`
response header with the configured `COOKIE_DOMAIN` value. This header tells the
auth service (or a downstream response transformer) what domain to use when setting
the `Set-Cookie` header.

The CORS plugin on these routes also exposes `Set-Cookie` in `expose_headers` so the
browser can see the cookie in cross-origin responses.

**Environment variable**: `COOKIE_DOMAIN`

| Environment | Value | Where set |
|-------------|-------|-----------|
| Local | `localhost` | consul-apisix-sync Deployment/CronJob env |
| Staging | `.isa-cloud.example.com` | consul-apisix-sync Deployment/CronJob env |
| Production | `.isa-cloud.example.com` | consul-apisix-sync Deployment/CronJob env |

### Layer 2: Auth Service (isA_user) — TODO

The auth service currently returns refresh tokens only in the JSON response body.
For cross-zone SSO, it needs to also set them as HttpOnly cookies. The auth service
should read the `COOKIE_DOMAIN` env var (or the `X-Auth-Cookie-Domain` header
injected by APISIX) and set the cookie accordingly.

#### Required changes in `isA_user/microservices/auth_service/main.py`

**1. Add `COOKIE_DOMAIN` config**

```python
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "localhost")
```

**2. Modify the login endpoint to set a cookie**

```python
@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest, ...):
    result = await auth_service.login(...)
    if not result.get("success"):
        raise HTTPException(...)

    response = JSONResponse(content=LoginResponse(...).model_dump())

    # Set refresh token as HttpOnly cookie on root domain
    if result.get("refresh_token"):
        response.set_cookie(
            key="refresh_token",
            value=result["refresh_token"],
            domain=COOKIE_DOMAIN,
            path="/",
            httponly=True,
            secure=True,       # Requires HTTPS (always True except local dev)
            samesite="lax",    # Allows navigation but blocks CSRF
            max_age=604800,    # 7 days (matches refresh token expiry)
        )

    return response
```

**3. Apply the same pattern to `/api/v1/auth/refresh` and `/api/v1/auth/verify`**

Both endpoints should set/update the `refresh_token` cookie when they issue tokens.

**4. Add a logout endpoint that clears the cookie**

```python
@app.post("/api/v1/auth/logout")
async def logout():
    response = JSONResponse(content={"success": True})
    response.delete_cookie(
        key="refresh_token",
        domain=COOKIE_DOMAIN,
        path="/",
    )
    return response
```

**5. Modify the refresh endpoint to also read the cookie**

```python
@app.post("/api/v1/auth/refresh")
async def refresh_token(
    request: Request,
    body: Optional[RefreshTokenRequest] = None,
    ...
):
    # Prefer body, fall back to cookie
    token = None
    if body and body.refresh_token:
        token = body.refresh_token
    else:
        token = request.cookies.get("refresh_token")

    if not token:
        raise HTTPException(status_code=401, detail="No refresh token provided")

    result = await auth_service.refresh_access_token(token)
    ...
```

### Layer 3: Frontend (isA_) — TODO

The frontend currently stores tokens in-memory. It needs to be updated to:

1. **On login/register**: Still store the access_token in-memory, but stop storing
   the refresh_token (it will be in an HttpOnly cookie, inaccessible to JS).
2. **On refresh**: Call `/api/v1/auth/refresh` with `credentials: 'include'` so the
   browser sends the HttpOnly cookie automatically. No need to pass the refresh
   token in the request body.
3. **On logout**: Call `/api/v1/auth/logout` with `credentials: 'include'` to clear
   the cookie.

## Cookie Security Properties

| Property | Value | Rationale |
|----------|-------|-----------|
| `httpOnly` | `true` | Prevents JavaScript access (XSS protection) |
| `secure` | `true` | Cookie only sent over HTTPS |
| `sameSite` | `lax` | Allows top-level navigation but blocks CSRF POST requests |
| `domain` | `COOKIE_DOMAIN` | Root domain for cross-zone access |
| `path` | `/` | Available to all paths |
| `max_age` | `604800` | 7 days (matches refresh token TTL) |

## Testing

After deploying, verify with:

```bash
# Login and check for Set-Cookie header
curl -v -X POST http://localhost:30080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}' \
  2>&1 | grep -i set-cookie

# Should show:
# Set-Cookie: refresh_token=<jwt>; Domain=localhost; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800

# Verify X-Auth-Cookie-Domain header is present
curl -v -X POST http://localhost:30080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}' \
  2>&1 | grep -i x-auth-cookie-domain

# Should show:
# X-Auth-Cookie-Domain: localhost
```
