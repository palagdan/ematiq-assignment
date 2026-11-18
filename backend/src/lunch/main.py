import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from typing import cast

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from lunch.auth.deps import CurrentUser
from lunch.auth.router import router as auth_router
from lunch.config import get_settings
from lunch.errors import DomainError
from lunch.history.router import router as history_router
from lunch.housekeeping import Housekeeper
from lunch.mailer import SmtpMailer
from lunch.models import Currency
from lunch.ratelimit import TooManyRequests
from lunch.rates_client import RatesClient, RatesProvider
from lunch.rooms.events import RoomEventListener, asyncpg_dsn
from lunch.rooms.hub import RoomHub
from lunch.rooms.router import router as rooms_router
from lunch.rooms.router import ws_router

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(timeout=2.0) as http:
        app.state.rates = RatesClient(settings.rates_url, http)
        app.state.hub = RoomHub()
        events = RoomEventListener(asyncpg_dsn(settings.database_url), app.state.hub)
        await events.start()
        app.state.mailer = SmtpMailer(
            settings.smtp_host,
            settings.smtp_port,
            settings.mail_from,
            username=settings.smtp_username,
            password=settings.smtp_password,
            security=settings.smtp_security,
        )
        housekeeper = Housekeeper(app.state.rates, timedelta(minutes=settings.lobby_idle_minutes))
        housekeeper.start()
        try:
            yield
        finally:
            await housekeeper.stop()
            await events.stop()


app = FastAPI(title="Lunch Roulette", lifespan=lifespan)
# Only holds OAuth state/nonce/PKCE verifier during the Google redirect dance.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="lunch_oauth",
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.include_router(auth_router)
app.include_router(rooms_router)
app.include_router(history_router)
app.include_router(ws_router)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, TooManyRequests) else None
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/rates")
async def rates(request: Request, _: CurrentUser) -> dict[Currency, Decimal]:
    return await cast(RatesProvider, request.app.state.rates).get_rates()
