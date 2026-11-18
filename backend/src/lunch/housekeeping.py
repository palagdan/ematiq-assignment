"""Background housekeeping.

- Running games: when the player on turn misses their deadline, they lose and pay.
- Lobbies: a lobby nobody touched for `lobby_idle` is deleted, freeing its players.
- Auth: expired sessions, password-reset tokens and old rate-limit windows are purged, so
  those tables don't grow forever.

Every backend process runs one. That's safe: expiring a turn re-checks the deadline under the
room's row lock, and the other jobs are single conditional DELETEs. Whichever worker gets
there first does the work, and the others find nothing left to do.
"""

import asyncio
import logging
import time
from datetime import timedelta

from lunch import ratelimit
from lunch.auth import service as auth_service
from lunch.db import SessionLocal
from lunch.rates_client import RatesProvider
from lunch.rooms import service

log = logging.getLogger(__name__)

TURN_CHECK_SECONDS = 1.0
LOBBY_CHECK_SECONDS = 60.0
AUTH_PURGE_SECONDS = 3600.0


class Housekeeper:
    def __init__(self, rates: RatesProvider, lobby_idle: timedelta) -> None:
        self._rates = rates
        self._lobby_idle = lobby_idle
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="housekeeping")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        next_lobby_check = next_auth_purge = 0.0
        while True:
            try:
                await self.expire_turns()
                if time.monotonic() >= next_lobby_check:
                    await self.expire_lobbies()
                    next_lobby_check = time.monotonic() + LOBBY_CHECK_SECONDS
                if time.monotonic() >= next_auth_purge:
                    await self.purge_expired_auth()
                    await ratelimit.purge_old_windows()
                    next_auth_purge = time.monotonic() + AUTH_PURGE_SECONDS
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("housekeeping pass failed")
            await asyncio.sleep(TURN_CHECK_SECONDS)

    async def expire_turns(self) -> list[str]:
        async with SessionLocal() as db:
            codes = await service.expired_turn_codes(db)
        if not codes:
            return []
        rates = await self._rates.get_rates()
        expired = []
        for code in codes:
            async with SessionLocal() as db:
                if await service.expire_turn(db, code, rates) is not None:
                    expired.append(code)
        if expired:
            log.info("turn timer ran out in rooms %s", ", ".join(expired))
        return expired

    async def expire_lobbies(self) -> list[str]:
        async with SessionLocal() as db:
            codes = await service.expire_idle_lobbies(db, self._lobby_idle)
        if codes:
            log.info("expired idle lobbies %s", ", ".join(codes))
        return codes

    async def purge_expired_auth(self) -> tuple[int, int]:
        async with SessionLocal() as db:
            sessions, tokens = await auth_service.purge_expired(db)
        if sessions or tokens:
            log.info("purged %d expired sessions and %d reset tokens", sessions, tokens)
        return sessions, tokens
