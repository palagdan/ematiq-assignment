"""Nobody gets stuck: turn timers, idle-lobby expiry and removing absent players."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from sqlalchemy import event, update

from lunch.db import SessionLocal, engine
from lunch.housekeeping import Housekeeper
from lunch.models import Room
from tests.conftest import BASE_URL, ClientFactory, FakeRates
from tests.test_rooms import setup_game
from tests.test_ws import socket_client


def sweeper() -> Housekeeper:
    return Housekeeper(FakeRates(), lobby_idle=timedelta(minutes=30))


async def age_room(code: str, **values: object) -> None:
    async with SessionLocal() as db:
        await db.execute(update(Room).where(Room.code == code).values(**values))
        await db.commit()


async def test_host_picks_turn_time(make_user: ClientFactory) -> None:
    alice, bob = await make_user("alice"), await make_user("bob")
    code = (await alice.post("/api/rooms")).json()["code"]
    await bob.post(f"/api/rooms/{code}/join")
    assert (await alice.get(f"/api/rooms/{code}")).json()["turn_seconds"] == 60

    room = (await alice.patch(f"/api/rooms/{code}", json={"turn_seconds": 30})).json()
    assert room["turn_seconds"] == 30
    assert (await alice.patch(f"/api/rooms/{code}", json={"turn_seconds": 7})).status_code == 400
    assert (await bob.patch(f"/api/rooms/{code}", json={"turn_seconds": 120})).status_code == 403


async def test_moves_reset_the_turn_deadline(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user, grid_size=16)
    deadline = datetime.fromisoformat(room["turn_deadline"])
    server_time = datetime.fromisoformat(room["server_time"])
    assert timedelta(seconds=55) < deadline - server_time <= timedelta(seconds=60)

    async with SessionLocal() as db:
        bomb = await db.scalar(
            Room.__table__.select().with_only_columns(Room.bomb_index).where(Room.code == code)
        )
    safe = next(c for c in range(16) if c != bomb)
    await age_room(code, turn_deadline=datetime.now(UTC) + timedelta(seconds=5))
    moved = (
        await clients[room["current_player_id"]].post(
            f"/api/rooms/{code}/moves", json={"cell": safe}
        )
    ).json()
    assert datetime.fromisoformat(moved["turn_deadline"]) - datetime.fromisoformat(
        moved["server_time"]
    ) > timedelta(seconds=55)


async def test_running_out_of_time_means_paying(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user)
    slowpoke = room["current_player_id"]

    assert await sweeper().expire_turns() == []  # deadline not reached yet
    await age_room(code, turn_deadline=datetime.now(UTC) - timedelta(seconds=1))
    assert await sweeper().expire_turns() == [code]
    assert await sweeper().expire_turns() == []  # already handled

    finished = (await clients[slowpoke].get(f"/api/rooms/{code}")).json()
    assert finished["status"] == "finished"
    assert finished["loser_id"] == slowpoke
    assert finished["finish_reason"] == "timeout"
    assert finished["turn_deadline"] is None
    assert finished["totals"] is not None
    for client in clients.values():
        assert (await client.get("/api/rooms/current")).json() is None
    history = (await clients[slowpoke].get("/api/history")).json()["items"]
    assert history[0]["finish_reason"] == "timeout"


async def test_workers_racing_to_expire_a_turn_do_it_once(make_user: ClientFactory) -> None:
    code, _, _ = await setup_game(make_user)
    await age_room(code, turn_deadline=datetime.now(UTC) - timedelta(seconds=1))
    results = await asyncio.gather(*(sweeper().expire_turns() for _ in range(4)))
    assert sorted(len(r) for r in results) == [0, 0, 0, 1]


async def test_idle_lobbies_expire_and_open_pages_are_told(make_user: ClientFactory) -> None:
    alice, bob = await make_user("alice"), await make_user("bob")
    idle = (await alice.post("/api/rooms")).json()["code"]
    busy = (await bob.post("/api/rooms")).json()["code"]
    await age_room(idle, last_activity_at=datetime.now(UTC) - timedelta(minutes=31))

    async with (
        socket_client(alice.cookies) as client,
        aconnect_ws(
            f"{BASE_URL}/ws/rooms/{idle}", client, session_class=AsyncWebSocketSession
        ) as ws,
    ):
        assert (await ws.receive_json())["type"] == "room.state"
        assert await sweeper().expire_lobbies() == [idle]
        assert await asyncio.wait_for(ws.receive_json(), 5) == {"type": "room.closed"}

    assert (await alice.get(f"/api/rooms/{idle}")).status_code == 404
    assert (await alice.get("/api/rooms/current")).json() is None
    assert (await bob.get(f"/api/rooms/{busy}")).status_code == 200


async def test_host_removes_absent_player(make_user: ClientFactory) -> None:
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    code = (await alice.post("/api/rooms")).json()["code"]
    await bob.post(f"/api/rooms/{code}/join")
    await carol.post(f"/api/rooms/{code}/join")
    ids = {
        p["username"]: p["user_id"]
        for p in (await alice.get(f"/api/rooms/{code}")).json()["players"]
    }

    assert (await bob.delete(f"/api/rooms/{code}/players/{ids['carol']}")).status_code == 403
    assert (await alice.delete(f"/api/rooms/{code}/players/{ids['alice']}")).status_code == 400
    assert (await alice.delete(f"/api/rooms/{code}/players/999999")).status_code == 404

    room = (await alice.delete(f"/api/rooms/{code}/players/{ids['bob']}")).json()
    assert [p["username"] for p in room["players"]] == ["alice", "carol"]
    assert (await bob.get("/api/rooms/current")).json() is None  # bob is free again


async def test_cannot_remove_players_mid_game(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user)
    host = room["host_id"]
    other = next(uid for uid in clients if uid != host)
    assert (await clients[host].delete(f"/api/rooms/{code}/players/{other}")).status_code == 409


@pytest.fixture
def statements() -> Iterator[list[str]]:
    seen: list[str] = []

    def record(conn: object, cursor: object, statement: str, *args: object) -> None:
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    yield seen
    event.remove(engine.sync_engine, "before_cursor_execute", record)


async def test_a_move_reads_the_room_once(make_user: ClientFactory, statements: list[str]) -> None:
    code, clients, room = await setup_game(make_user, grid_size=16)
    async with SessionLocal() as db:
        bomb = await db.scalar(
            Room.__table__.select().with_only_columns(Room.bomb_index).where(Room.code == code)
        )
    safe = next(c for c in range(16) if c != bomb)
    on_turn = clients[room["current_player_id"]]

    statements.clear()
    response = await on_turn.post(f"/api/rooms/{code}/moves", json={"cell": safe})
    assert response.status_code == 200
    assert response.json()["moves"][0]["at"] is not None  # server default came back with the INSERT
    room_reads = [s for s in statements if s.lstrip().startswith("SELECT") and "FROM rooms" in s]
    assert len(room_reads) == 1, room_reads


async def test_background_loop_enforces_deadlines(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user)
    await age_room(code, turn_deadline=datetime.now(UTC) - timedelta(seconds=1))
    loop = sweeper()
    loop.start()
    try:
        for _ in range(50):
            state = (await clients[room["host_id"]].get(f"/api/rooms/{code}")).json()
            if state["status"] == "finished":
                break
            await asyncio.sleep(0.1)
    finally:
        await loop.stop()
    assert state["finish_reason"] == "timeout"
