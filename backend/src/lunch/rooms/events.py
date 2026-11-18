"""Cross-process fan-out of room changes via Postgres LISTEN/NOTIFY.

Every room command calls `pg_notify(CHANNEL, code)` inside its transaction, so Postgres
delivers the notification only once the change commits, in commit order. Each backend
process (worker or replica) runs one `RoomEventListener`. It holds a dedicated LISTEN
connection, reloads the snapshot of a room it has sockets in, and pushes it through its
local `RoomHub`. The payload is just the room code: snapshots can exceed NOTIFY's 8 kB limit.

Clients keep the snapshot with the highest `version`, so duplicate or reordered pushes are
harmless. That makes it safe to re-send everything after a reconnect.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg

from lunch.db import SessionLocal
from lunch.errors import NotFound
from lunch.rooms import service
from lunch.rooms.hub import RoomHub
from lunch.rooms.schemas import RoomOut
from lunch.rooms.service import ROOM_EVENTS_CHANNEL as CHANNEL

log = logging.getLogger(__name__)

# How often an idle LISTEN connection is pinged, so a silently dropped one is noticed.
KEEPALIVE_SECONDS = 15.0
# How long startup waits for the first LISTEN before carrying on (it keeps retrying).
STARTUP_WAIT_SECONDS = 10.0

Snapshot = Callable[[str], Awaitable[dict[str, Any] | None]]


def state_message(room: RoomOut) -> dict[str, Any]:
    return {"type": "room.state", "room": room.model_dump(mode="json")}


async def load_state_message(code: str) -> dict[str, Any] | None:
    """The current snapshot of a room, or None if it no longer exists."""
    async with SessionLocal() as db:
        try:
            room = await service.load_room(db, code)
        except NotFound:
            return None
        return state_message(RoomOut.from_room(room))


def asyncpg_dsn(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class RoomEventListener:
    def __init__(self, dsn: str, hub: RoomHub, snapshot: Snapshot = load_state_message) -> None:
        self._dsn = dsn
        self._hub = hub
        self._snapshot = snapshot
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._connection: asyncpg.Connection | None = None
        # Rooms with a push in flight, and rooms that changed again meanwhile.
        self._pushing: set[str] = set()
        self._dirty: set[str] = set()
        self._push_tasks: set[asyncio.Task[None]] = set()

    @property
    def server_pid(self) -> int | None:
        """Backend PID of the LISTEN connection (used by tests to simulate a dropped link)."""
        return self._connection.get_server_pid() if self._connection else None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="room-event-listener")
        try:
            await asyncio.wait_for(self._ready.wait(), STARTUP_WAIT_SECONDS)
        except TimeoutError:
            log.warning("room event listener not connected yet; it keeps retrying")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        for task in list(self._push_tasks):
            task.cancel()
        await asyncio.gather(*self._push_tasks, return_exceptions=True)

    async def wait_connected(self) -> None:
        await self._ready.wait()

    async def _run(self) -> None:
        backoff = 0.5
        while True:
            try:
                await self._listen()
                backoff = 0.5
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("room event listener lost its connection: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    async def _listen(self) -> None:
        connection: asyncpg.Connection = await asyncpg.connect(self._dsn)
        closed = asyncio.Event()
        connection.add_termination_listener(lambda _conn: closed.set())
        try:
            await connection.add_listener(CHANNEL, self._on_notify)
            self._connection = connection
            self._ready.set()
            # Anything committed while we were disconnected was missed: refresh every room.
            for code in self._hub.rooms():
                self.schedule(code)
            while not closed.is_set():
                try:
                    await asyncio.wait_for(closed.wait(), KEEPALIVE_SECONDS)
                except TimeoutError:
                    await connection.execute("SELECT 1")
            raise ConnectionError("LISTEN connection closed")
        finally:
            self._ready.clear()
            self._connection = None
            if not connection.is_closed():
                await connection.close(timeout=2)

    def _on_notify(self, _conn: Any, _pid: int, _channel: str, code: str) -> None:
        self.schedule(code)

    def schedule(self, code: str) -> None:
        if not self._hub.has(code):
            return
        if code in self._pushing:
            self._dirty.add(code)
            return
        self._pushing.add(code)
        task = asyncio.create_task(self._push(code))
        self._push_tasks.add(task)
        task.add_done_callback(self._push_tasks.discard)

    async def _push(self, code: str) -> None:
        try:
            while True:
                self._dirty.discard(code)
                message = await self._snapshot(code)
                if message is None:
                    # Deleted (e.g. an idle lobby expired): tell open pages instead of going quiet.
                    self._hub.publish_control(code, {"type": "room.closed"})
                else:
                    self._hub.publish(code, message)  # never waits on clients
                if code not in self._dirty:
                    return
        except Exception:
            log.exception("could not push room %s", code)
        finally:
            self._pushing.discard(code)
