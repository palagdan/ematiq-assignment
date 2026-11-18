"""Data hygiene and integrity: auth GC, resilient history, immutable game records."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from lunch.db import SessionLocal
from lunch.housekeeping import Housekeeper
from lunch.models import AuthSession, OAuthIdentity, PasswordResetToken, Room, User
from tests.conftest import ClientFactory, FakeRates
from tests.test_history import play_and_give_up


def housekeeper() -> Housekeeper:
    return Housekeeper(FakeRates(), lobby_idle=timedelta(minutes=30))


async def count(model: type[AuthSession] | type[PasswordResetToken]) -> int:
    async with SessionLocal() as db:
        return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def test_expired_sessions_and_reset_tokens_are_purged(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    await make_user("bob")
    for _ in range(2):
        await alice.post("/api/auth/password/forgot", json={"email": "alice@example.com"})
    await alice.post("/api/auth/password/forgot", json={"email": "bob@example.com"})
    past = datetime.now(UTC) - timedelta(seconds=1)
    async with SessionLocal() as db:
        bob_id = await db.scalar(select(User.id).where(User.username == "bob"))
        await db.execute(
            update(AuthSession).where(AuthSession.user_id == bob_id).values(expires_at=past)
        )
        await db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == bob_id)
            .values(expires_at=past)
        )
        await db.commit()
    assert (await count(AuthSession), await count(PasswordResetToken)) == (2, 2)

    assert await housekeeper().purge_expired_auth() == (1, 1)
    assert (await count(AuthSession), await count(PasswordResetToken)) == (1, 1)
    assert (await alice.get("/api/auth/me")).status_code == 200  # live session untouched
    assert await housekeeper().purge_expired_auth() == (0, 0)


async def test_history_survives_an_inconsistent_record(
    make_user: ClientFactory, caplog: pytest.LogCaptureFixture
) -> None:
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    broken = await play_and_give_up(alice, bob)
    await play_and_give_up(alice, carol)
    async with SessionLocal() as db:  # point the payer at someone who wasn't in that game
        carol_id = await db.scalar(select(User.id).where(User.username == "carol"))
        await db.execute(update(Room).where(Room.code == broken).values(loser_id=carol_id))
        await db.commit()

    response = await alice.get("/api/history")
    assert response.status_code == 200
    entries = {e["code"]: e for e in response.json()["items"]}
    assert entries[broken]["loser_username"] == "unknown player"
    assert len(entries) == 2  # the healthy game is still listed
    assert f"finished room {broken} has no player row" in caplog.text


async def test_players_with_game_history_cannot_be_hard_deleted(make_user: ClientFactory) -> None:
    alice, bob = await make_user("alice"), await make_user("bob")
    await play_and_give_up(alice, bob)
    async with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            await db.execute(delete(User).where(User.username == "bob"))
            await db.commit()


async def test_players_without_games_can_be_deleted_with_their_auth_data(
    make_user: ClientFactory,
) -> None:
    dave = await make_user("dave")
    await dave.post("/api/auth/password/forgot", json={"email": "dave@example.com"})
    async with SessionLocal() as db:
        dave_id = await db.scalar(select(User.id).where(User.username == "dave"))
        db.add(OAuthIdentity(user_id=dave_id, provider="google", subject="g-dave", email=None))
        await db.commit()
        await db.execute(delete(User).where(User.id == dave_id))
        await db.commit()
        for model in (AuthSession, PasswordResetToken, OAuthIdentity):
            left = await db.scalar(
                select(func.count()).select_from(model).where(model.user_id == dave_id)
            )
            assert left == 0
