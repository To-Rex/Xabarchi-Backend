"""Smoke test: the app imports, builds, and serves /healthz without any
infrastructure (no PostgreSQL, no Redis).

/readyz is deliberately NOT exercised — it pings real dependencies.
The TestClient is used WITHOUT its context manager so the lifespan (Redis
init + lease reaper) never runs.
"""

from __future__ import annotations

import os

# Provide config before app.core.config is imported, so the test suite works
# even without a .env file (CI). Real values are irrelevant: nothing connects.
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/xabarchi_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")

from fastapi.testclient import TestClient  # noqa: E402


def test_app_creates() -> None:
    from app.main import app, create_app

    assert app.title == "Xabarchi API"
    assert create_app().version == "1.0.0"


def test_healthz_ok() -> None:
    from app.main import app

    client = TestClient(app)  # no `with`: lifespan intentionally skipped
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_lists_core_routes() -> None:
    from app.main import app

    # FastAPI >= 0.141 keeps included routers nested (_IncludedRouter) instead
    # of flattening them into the app's route list; support both shapes.
    paths: set[str] = set()
    for route in app.routes:
        context = getattr(route, "include_context", None)
        if context is not None:
            prefix = context.prefix or ""
            paths.update(prefix + sub.path for sub in route.original_router.routes)
        else:
            paths.add(route.path)
    for expected in (
        "/healthz",
        "/readyz",
        "/api/v1/auth/login",
        "/api/v1/auth/password/forgot",
        "/api/v1/auth/password/reset",
        "/api/v1/auth/email/verify",
        "/api/v1/auth/oauth/{provider}/start",
        "/api/v1/auth/oauth/{provider}/callback",
        "/api/v1/devices/pair/start",
        "/api/v1/devices/pair/complete",
        "/api/v1/messages",
        "/api/v1/gateway/claim",
        "/api/v1/ws",
        "/api/v1/billing/checkout",
        "/api/v1/billing/portal",
        "/api/v1/billing/webhook/polar",
    ):
        assert expected in paths, f"missing route: {expected}"


def test_polar_webhook_signature() -> None:
    """Round-trip the Standard Webhooks HMAC scheme used by Polar."""
    import base64
    import hashlib
    import hmac
    import time

    from app.core.config import settings
    from app.core.exceptions import AuthError
    from app.services.polar_service import verify_webhook

    secret_bytes = b"test-webhook-secret-32-bytes-long!"
    settings.polar_webhook_secret = "whsec_" + base64.b64encode(secret_bytes).decode()

    body = b'{"type":"order.paid","data":{"id":"ord_1"}}'
    webhook_id = "msg_123"
    timestamp = str(int(time.time()))
    signed = f"{webhook_id}.{timestamp}.".encode() + body
    signature = base64.b64encode(hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode()
    headers = {
        "webhook-id": webhook_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": f"v1,{signature}",
    }

    verify_webhook(body, headers)  # must not raise

    for bad_headers, bad_body in (
        ({**headers, "webhook-signature": "v1,dGFtcGVyZWQ="}, body),  # wrong signature
        (headers, body + b" "),  # tampered body
        ({**headers, "webhook-timestamp": str(int(time.time()) - 3600)}, body),  # stale
    ):
        try:
            verify_webhook(bad_body, bad_headers)
        except AuthError:
            pass
        else:
            raise AssertionError("verify_webhook accepted an invalid signature")
