import asyncio
from typing import Any, cast

import pytest
from fastapi import WebSocket

from lunch.rooms import hub as hub_module
from lunch.rooms.hub import RoomHub


def snapshot(version: int) -> dict[str, Any]:
    return {"type": "room.state", "room": {"version": version}}


class FakeSocket:
    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken
        self.gate = asyncio.Event()  # a closed gate simulates a client that isn't reading
        self.gate.set()
        self.received: asyncio.Queue[int] = asyncio.Queue()
        self.closed_with: int | None = None

    async def send_json(self, message: dict[str, Any]) -> None:
        if self.broken:
            raise RuntimeError("connection closed")
        await self.gate.wait()
        await self.received.put(message["room"]["version"])

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code

    async def next(self) -> int:
        return await asyncio.wait_for(self.received.get(), timeout=2)


def ws(fake: FakeSocket) -> WebSocket:
    return cast(WebSocket, fake)


async def test_publish_reaches_only_that_room() -> None:
    hub = RoomHub()
    here, elsewhere = FakeSocket(), FakeSocket()
    hub.add("AAAAAA", ws(here))
    hub.add("BBBBBB", ws(elsewhere))
    hub.publish("AAAAAA", snapshot(1))
    assert await here.next() == 1
    assert elsewhere.received.empty()


async def test_frozen_client_does_not_delay_others() -> None:
    hub = RoomHub()
    frozen, fast = FakeSocket(), FakeSocket()
    frozen.gate.clear()
    hub.add("AAAAAA", ws(frozen))
    hub.add("AAAAAA", ws(fast))

    hub.publish("AAAAAA", snapshot(1))  # returns at once, no awaiting clients
    assert await fast.next() == 1
    hub.publish("AAAAAA", snapshot(2))
    assert await fast.next() == 2
    assert frozen.received.empty()


async def test_slow_client_gets_latest_state_and_never_goes_back() -> None:
    hub = RoomHub()
    slow = FakeSocket()
    slow.gate.clear()
    hub.add("AAAAAA", ws(slow))

    hub.publish("AAAAAA", snapshot(1))  # picked up and stuck sending
    await asyncio.sleep(0)
    for version in (2, 3, 4):
        hub.publish("AAAAAA", snapshot(version))
    hub.send("AAAAAA", ws(slow), snapshot(3))  # an older snapshot arriving late is ignored
    slow.gate.set()
    assert await slow.next() == 1
    assert await slow.next() == 4  # 2 and 3 were superseded
    hub.publish("AAAAAA", snapshot(4))  # already delivered
    await asyncio.sleep(0.05)
    assert slow.received.empty()


async def test_stalled_client_is_closed_and_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hub_module, "SEND_TIMEOUT_SECONDS", 0.05)
    hub = RoomHub()
    stalled = FakeSocket()
    stalled.gate.clear()
    hub.add("AAAAAA", ws(stalled))
    hub.publish("AAAAAA", snapshot(1))
    await asyncio.sleep(0.2)
    assert stalled.closed_with == 1011
    assert not hub.has("AAAAAA")


async def test_dead_client_is_dropped() -> None:
    hub = RoomHub()
    dead, alive = FakeSocket(broken=True), FakeSocket()
    hub.add("AAAAAA", ws(dead))
    hub.add("AAAAAA", ws(alive))
    hub.publish("AAAAAA", snapshot(1))
    assert await alive.next() == 1
    await asyncio.sleep(0.05)
    assert hub.rooms() == ["AAAAAA"]
    hub.publish("AAAAAA", snapshot(2))
    assert await alive.next() == 2


async def test_remove_is_idempotent() -> None:
    hub = RoomHub()
    socket = ws(FakeSocket())
    hub.remove("NOROOM", socket)
    hub.add("AAAAAA", socket)
    hub.add("AAAAAA", socket)  # adding twice keeps one outbox
    hub.remove("AAAAAA", socket)
    hub.remove("AAAAAA", socket)
    assert not hub.has("AAAAAA")
    hub.publish("AAAAAA", snapshot(1))  # nobody left, nothing to do
    hub.send("AAAAAA", socket, snapshot(1))


async def test_control_messages_skip_versioning() -> None:
    hub = RoomHub()
    socket = FakeSocket()
    sent: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        sent.append(message)

    socket.send_json = record  # type: ignore[method-assign]
    hub.add("AAAAAA", ws(socket))
    hub.publish("AAAAAA", snapshot(3))
    await asyncio.sleep(0.01)
    hub.send_control("AAAAAA", ws(socket), {"type": "pong"})
    hub.send_control("AAAAAA", ws(socket), {"type": "pong"})  # pongs are never "too old"
    await asyncio.sleep(0.01)
    assert sent == [snapshot(3), {"type": "pong"}]
    hub.send_control("NOROOM", ws(socket), {"type": "pong"})  # unknown socket: ignored
