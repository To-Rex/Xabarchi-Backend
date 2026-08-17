"""Application factory and process lifecycle.

``create_app()`` wires logging, CORS, the AppError -> JSON envelope, every
router, the WebSocket relay, and a lifespan that runs the lease reaper —
the background loop returning expired gateway leases to the queue.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1 import (
    admin,
    analytics,
    apikeys,
    auth,
    billing,
    contacts,
    devices,
    gateway,
    health,
    messages,
    notifications,
    telegram,
    templates,
    ws,
)
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.infrastructure.db.session import async_session_factory, engine
from app.infrastructure.redis.client import close_redis, get_redis
from app.repositories import message_repo

logger = logging.getLogger(__name__)

_REAPER_INTERVAL_SECONDS = 30.0

API_V1_PREFIX = "/api/v1"


async def _lease_reaper() -> None:
    """Every 30s: requeue (or fail out) messages whose device lease expired."""
    while True:
        await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
        try:
            async with async_session_factory() as session:
                count = await message_repo.requeue_expired_leases(session)
                await session.commit()
            if count:
                logger.info("Lease reaper requeued/failed %d expired message(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the reaper must survive anything
            logger.exception("Lease reaper iteration failed")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_redis()  # eager init so the first request doesn't pay for it
    reaper = asyncio.create_task(_lease_reaper(), name="lease-reaper")
    logger.info("Xabarchi API started (env=%s)", settings.app_env)
    try:
        yield
    finally:
        reaper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reaper
        await close_redis()
        await engine.dispose()
        logger.info("Xabarchi API shut down cleanly")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Xabarchi API",
        version="1.0.0",
        default_response_class=ORJSONResponse,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> ORJSONResponse:
        return ORJSONResponse(status_code=exc.status, content=exc.to_dict())

    # Probes live at the root so orchestrators don't need the API prefix.
    app.include_router(health.router)

    for module in (
        auth,
        devices,
        messages,
        gateway,
        contacts,
        templates,
        telegram,
        notifications,
        analytics,
        apikeys,
        billing,
        admin,
        ws,
    ):
        app.include_router(module.router, prefix=API_V1_PREFIX)

    return app


app = create_app()
