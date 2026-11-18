"""Room changes reach sockets in every backend process, via Postgres LISTEN/NOTIFY."""

import asyncio
import os
from typing import Any, cast

import asyncpg
from fastapi import WebSocket

from lunch.rooms.events import RoomEventListener, asyncpg_dsn
from lunch.rooms.hub import RoomHub
from tests.conftest import ClientFactory

DSN = asyncpg_dsn(os.environ["LUNCH_DATABASE_URL"])


class FakeSocket:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def send_json(self, message: dict[str, Any]) -> None:
        await self.messages.put(message)

    async def next_version(self) -> int:
        message = await asyncio.wait_for(self.messages.get(), timeout=5)
        return int(message["room"]["version"])


class Worker:
    """Stands in for one backend process: its own hub and its own LISTEN connection."""

    def __init__(self) -> None:
        self.hub = RoomHub()
        self.events = RoomEventListener(DSN, self.hub)

    def watch(self, code: str) -> FakeSocket:
        socket = FakeSocket()
        self.hub.add(code, cast(WebSocket, socket))
        return socket


async def test_change_reaches_sockets_on_every_worker(make_user: ClientFactory) -> None:
    alice, bob = await make_user("alice"), await make_user("bob")
    code = (await alice.post("/api/rooms")).json()["code"]
    first, second = Worker(), Worker()
    await first.events.start()
    await second.events.start()
    try:
        on_first, on_second = first.watch(code), second.watch(code)
        # The request is handled by "another" process (the app's own worker).
        await bob.post(f"/api/rooms/{code}/join")
        assert await on_first.next_version() == 1
        assert await on_second.next_version() == 1
    finally:
        await first.events.stop()
        await second.events.stop()


async def test_rolled_back_changes_are_not_announced(make_user: ClientFactory) -> None:
    alice = await make_user("alice")
    code = (await alice.post("/api/rooms")).json()["code"]
    worker = Worker()
    await worker.events.start()
    try:
        socket = worker.watch(code)
        # Rejected command: not enough players, so the transaction never commits.
        assert (await alice.post(f"/api/rooms/{code}/start")).status_code == 409
        await asyncio.sleep(0.3)
        assert socket.messages.empty()
    finally:
        await worker.events.stop()


async def test_reconnects_and_resyncs_after_losing_the_connection(make_user: ClientFactory) -> None:
    alice, bob = await make_user("alice"), await make_user("bob")
    code = (await alice.post("/api/rooms")).json()["code"]
    worker = Worker()
    await worker.events.start()
    try:
        socket = worker.watch(code)
        pid = worker.events.server_pid
        assert pid is not None

        admin = await asyncpg.connect(DSN)
        try:
            await admin.execute("SELECT pg_terminate_backend($1)", pid)
            # Committed while the listener is down: it must still be delivered after reconnecting.
            await bob.post(f"/api/rooms/{code}/join")
        finally:
            await admin.close()

        assert await socket.next_version() == 1
        assert worker.events.server_pid not in (None, pid)

        await bob.put(f"/api/rooms/{code}/meal", json={"amount": "9", "currency": "EUR"})
        versions = {await socket.next_version()}
        while not socket.messages.empty():
            versions.add(await socket.next_version())
        assert 2 in versions
    finally:
        await worker.events.stop()


async def test_bursts_are_coalesced_into_latest_state() -> None:
    hub = RoomHub()
    loads = 0
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_snapshot(code: str) -> dict[str, Any] | None:
        nonlocal loads
        loads += 1
        started.set()
        await release.wait()
        return {"type": "room.state", "room": {"version": loads}}

    listener = RoomEventListener(DSN, hub, snapshot=slow_snapshot)
    socket = FakeSocket()
    hub.add("AAAAAA", cast(WebSocket, socket))
    listener.schedule("AAAAAA")
    await started.wait()  # the first load is now running
    for _ in range(4):
        listener.schedule("AAAAAA")  # four more changes while it is still running
    listener.schedule("NOBODY")  # no local sockets: ignored without loading anything
    release.set()
    # One extra reload covers all four changes, and the client ends on the newest state
    # (the superseded snapshot is skipped by the socket's latest-wins outbox).
    assert await socket.next_version() == 2
    await asyncio.sleep(0.05)
    assert loads == 2
    assert socket.messages.empty()
    await listener.stop()
