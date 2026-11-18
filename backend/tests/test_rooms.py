import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from lunch.db import SessionLocal
from lunch.models import Room
from lunch.rooms import game
from lunch.rooms.game import commitment
from tests.conftest import ClientFactory


async def bomb_of(code: str) -> int:
    async with SessionLocal() as db:
        bomb = await db.scalar(select(Room.bomb_index).where(Room.code == code))
    assert bomb is not None
    return bomb


async def setup_game(
    make_user: ClientFactory, grid_size: int = 9
) -> tuple[str, dict[int, httpx.AsyncClient], dict[str, Any]]:
    """alice hosts, bob joins, both enter meals, game starts."""
    alice = await make_user("alice")
    bob = await make_user("bob")
    code = (await alice.post("/api/rooms")).json()["code"]
    assert (await bob.post(f"/api/rooms/{code}/join")).status_code == 200
    await alice.put(f"/api/rooms/{code}/meal", json={"amount": "250", "currency": "CZK"})
    await bob.put(f"/api/rooms/{code}/meal", json={"amount": "12.5", "currency": "EUR"})
    await alice.patch(f"/api/rooms/{code}", json={"grid_size": grid_size})
    started = await alice.post(f"/api/rooms/{code}/start")
    assert started.status_code == 200, started.text
    room = started.json()
    clients = {}
    for client in (alice, bob):
        me = (await client.get("/api/auth/me")).json()
        clients[me["id"]] = client
    return code, clients, room


async def test_lobby_flow(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    bob = await make_user("bob")
    code = (await alice.post("/api/rooms")).json()["code"]

    # Codes are case-insensitive.
    room = (await bob.post(f"/api/rooms/{code.lower()}/join")).json()
    assert [p["username"] for p in room["players"]] == ["alice", "bob"]

    not_ready = await alice.post(f"/api/rooms/{code}/start")
    assert not_ready.status_code == 409

    not_host = await bob.patch(f"/api/rooms/{code}", json={"grid_size": 16})
    assert not_host.status_code == 403

    await bob.post(f"/api/rooms/{code}/leave")
    room = (await alice.get(f"/api/rooms/{code}")).json()
    assert [p["username"] for p in room["players"]] == ["alice"]


async def test_full_game_and_history(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user)
    assert room["status"] == "playing"
    assert room["bomb_index"] is None and room["bomb_salt"] is None
    assert len(room["bomb_commitment"]) == 64

    bomb = await bomb_of(code)
    safe_cells = iter(c for c in range(9) if c != bomb)
    # Open safe cells until only the bomb is left; the next player has to hit it.
    while True:
        on_turn = clients[room["current_player_id"]]
        cell = next(safe_cells, bomb)
        response = await on_turn.post(f"/api/rooms/{code}/moves", json={"cell": cell})
        assert response.status_code == 200, response.text
        room = response.json()
        if room["status"] == "finished":
            break

    assert room["bomb_index"] == bomb
    assert room["finish_reason"] == "bomb"
    # Once the game is over nobody is stuck in it, and nothing new was created.
    for client in clients.values():
        assert (await client.get("/api/rooms/current")).json() is None
    assert commitment(room["bomb_index"], room["bomb_salt"]) == room["bomb_commitment"]
    # 250 CZK + 12.5 EUR * 25 = 562.50 CZK
    assert room["totals"]["CZK"] == "562.50"
    assert room["totals"]["EUR"] == "22.50"

    any_client = next(iter(clients.values()))
    history = (await any_client.get("/api/history")).json()
    assert history["has_more"] is False
    [entry] = history["items"]
    assert entry["code"] == code
    assert entry["loser_id"] == room["loser_id"]
    assert {(p["username"], p["meal_amount"], p["meal_currency"]) for p in entry["players"]} == {
        ("alice", "250.00000000", "CZK"),
        ("bob", "12.50000000", "EUR"),
    }
    assert sum(p["paid"] for p in entry["players"]) == 1


async def test_rules_enforced_during_game(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user, grid_size=16)
    bomb = await bomb_of(code)
    safe = next(c for c in range(16) if c != bomb)
    waiting = next(c for uid, c in clients.items() if uid != room["current_player_id"])

    out_of_turn = await waiting.post(f"/api/rooms/{code}/moves", json={"cell": safe})
    assert out_of_turn.status_code == 409

    outsider = await make_user("carol")
    assert (await outsider.post(f"/api/rooms/{code}/join")).status_code == 409
    not_member = await outsider.post(f"/api/rooms/{code}/moves", json={"cell": safe})
    assert not_member.status_code == 403

    # Outsiders can still watch, but never see the bomb.
    watched = (await outsider.get(f"/api/rooms/{code}")).json()
    assert watched["bomb_index"] is None


async def test_concurrent_moves_only_one_wins(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user, grid_size=16)
    bomb = await bomb_of(code)
    first, second = [c for c in range(16) if c != bomb][:2]
    on_turn = clients[room["current_player_id"]]

    responses = await asyncio.gather(
        on_turn.post(f"/api/rooms/{code}/moves", json={"cell": first}),
        on_turn.post(f"/api/rooms/{code}/moves", json={"cell": second}),
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    final = (await on_turn.get(f"/api/rooms/{code}")).json()
    assert len(final["moves"]) == 1


async def test_one_active_game_per_player(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    bob = await make_user("bob")
    assert (await alice.get("/api/rooms/current")).json() is None

    first = (await alice.post("/api/rooms")).json()["code"]
    assert (await alice.get("/api/rooms/current")).json()["code"] == first

    second_create = await alice.post("/api/rooms")
    assert second_create.status_code == 409
    assert first in second_create.json()["detail"]

    other = (await bob.post("/api/rooms")).json()["code"]
    assert (await alice.post(f"/api/rooms/{other}/join")).status_code == 409
    # Re-joining your own room is a harmless no-op.
    assert (await alice.post(f"/api/rooms/{first}/join")).status_code == 200

    await alice.post(f"/api/rooms/{first}/leave")
    assert (await alice.get("/api/rooms/current")).json() is None
    assert (await alice.post(f"/api/rooms/{other}/join")).status_code == 200


async def test_parallel_creates_yield_one_room(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    responses = await asyncio.gather(*(alice.post("/api/rooms") for _ in range(4)))
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409]


async def test_give_up_makes_you_pay_and_frees_you(make_user: ClientFactory) -> None:
    code, clients, room = await setup_game(make_user)
    quitter_id, quitter = next(iter(clients.items()))

    response = await quitter.post(f"/api/rooms/{code}/give-up")
    assert response.status_code == 200
    room = response.json()
    assert room["status"] == "finished"
    assert room["loser_id"] == quitter_id
    assert room["finish_reason"] == "gave_up"
    assert room["totals"] is not None

    assert (await quitter.get("/api/rooms/current")).json() is None
    assert (await quitter.post("/api/rooms")).status_code == 201


async def test_unknown_room_is_404(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    assert (await alice.get("/api/rooms/ZZZZZZ")).status_code == 404


async def test_host_leaving_hands_over_the_room(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    bob = await make_user("bob")
    code = (await alice.post("/api/rooms")).json()["code"]
    bob_id = (await bob.get("/api/auth/me")).json()["id"]
    await bob.post(f"/api/rooms/{code}/join")

    assert (await bob.post(f"/api/rooms/{code}/start")).status_code == 403
    await alice.post(f"/api/rooms/{code}/leave")
    room = (await bob.get(f"/api/rooms/{code}")).json()
    assert room["host_id"] == bob_id
    assert [p["username"] for p in room["players"]] == ["bob"]


async def test_room_is_full_at_max_players(make_user: ClientFactory) -> None:
    host = await make_user("host")
    code = (await host.post("/api/rooms")).json()["code"]
    for i in range(game.MAX_PLAYERS - 1):
        guest = await make_user(f"guest{i}")
        assert (await guest.post(f"/api/rooms/{code}/join")).status_code == 200
    late = await make_user("late")
    full = await late.post(f"/api/rooms/{code}/join")
    assert full.status_code == 409
    assert "full" in full.json()["detail"]


async def test_room_code_collisions_are_retried(
    make_user: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    codes = iter(["AAAAAA", "AAAAAA", "BBBBBB"])
    monkeypatch.setattr(game, "new_room_code", lambda: next(codes))
    alice = await make_user("alice")
    bob = await make_user("bob")
    assert (await alice.post("/api/rooms")).json()["code"] == "AAAAAA"
    assert (await bob.post("/api/rooms")).json()["code"] == "BBBBBB"

    monkeypatch.setattr(game, "new_room_code", lambda: "AAAAAA")
    carol = await make_user("carol")
    exhausted = await carol.post("/api/rooms")
    assert exhausted.status_code == 409
