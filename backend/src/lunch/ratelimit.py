import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from lunch.config import get_settings
from lunch.db import SessionLocal
from lunch.errors import DomainError
from lunch.models import RateLimitHit


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window: timedelta


LOGIN_PER_IP = Rule("login-ip", 60, timedelta(minutes=5))
LOGIN_PER_ACCOUNT = Rule("login-account", 10, timedelta(minutes=5))
REGISTER_PER_IP = Rule("register-ip", 20, timedelta(hours=1))
FORGOT_PER_IP = Rule("forgot-ip", 10, timedelta(hours=1))
FORGOT_PER_EMAIL = Rule("forgot-email", 3, timedelta(hours=1))
RESET_PER_IP = Rule("reset-ip", 20, timedelta(hours=1))
PASSWORD_CHANGE_PER_USER = Rule("password-change", 10, timedelta(minutes=15))
ROOM_CREATE_PER_USER = Rule("room-create", 30, timedelta(minutes=10))


class TooManyRequests(DomainError):
    status_code = 429

    def __init__(self, retry_after: int) -> None:
        amount, unit = (
            (retry_after, "second") if retry_after < 60 else (math.ceil(retry_after / 60), "minute")
        )
        wait = f"{amount} {unit}{'' if amount == 1 else 's'}"
        super().__init__(f"Too many attempts. Try again in {wait}.")
        self.retry_after = retry_after


def client_ip(request: Request) -> str:
    # uvicorn resolves this from X-Forwarded-For, which our nginx overwrites (not appends),
    # so clients can't spoof it.
    return request.client.host if request.client else "unknown"


def _key(rule: Rule, subject: str) -> str:
    return f"{rule.name}:{hashlib.sha256(subject.lower().encode()).hexdigest()[:40]}"


def _window_start(now: datetime, window: timedelta) -> datetime:
    size = int(window.total_seconds())
    return datetime.fromtimestamp(int(now.timestamp()) // size * size, UTC)


async def enforce(*checks: tuple[Rule, str]) -> None:
    """Count one hit for every (rule, subject); raise 429 if any rule is over its limit."""
    if not get_settings().rate_limits_enabled:
        return
    now = datetime.now(UTC)
    retry_after = 0
    async with SessionLocal() as db:
        for rule, subject in checks:
            start = _window_start(now, rule.window)
            stmt = insert(RateLimitHit).values(key=_key(rule, subject), window_start=start, hits=1)
            hits = await db.scalar(
                stmt.on_conflict_do_update(
                    index_elements=[RateLimitHit.key, RateLimitHit.window_start],
                    set_={"hits": RateLimitHit.hits + 1},
                ).returning(RateLimitHit.hits)
            )
            if hits is not None and hits > rule.limit:
                ends_in = (start + rule.window - now).total_seconds()
                retry_after = max(retry_after, math.ceil(ends_in))
        await db.commit()
    if retry_after:
        raise TooManyRequests(retry_after)


async def purge_old_windows(keep: timedelta = timedelta(days=1)) -> int:
    async with SessionLocal() as db:
        result = await db.execute(
            delete(RateLimitHit).where(RateLimitHit.window_start < datetime.now(UTC) - keep)
        )
        await db.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]
