import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)

# A socket that can't take a message within this time is considered stalled and closed;
# the client reconnects and gets a fresh snapshot.
SEND_TIMEOUT_SECONDS = 5.0


def _version(message: dict[str, Any]) -> int:
    return int(message.get("room", {}).get("version", 0))


class _Outbox:
    """One socket's sender. Holds only the newest snapshot, so a slow client skips
    intermediate states instead of building a backlog, and never goes backwards."""

    def __init__(self, ws: WebSocket, on_dead: Callable[[], None]) -> None:
        self._ws = ws
        self._on_dead = on_dead
        self._pending: dict[str, Any] | None = None
        # Unversioned messages such as heartbeat pongs; sent ahead of snapshots.
        self._control: dict[str, Any] | None = None
        self._sent_version = -1
        self._wake = asyncio.Event()
        self.task = asyncio.create_task(self._run())

    def put(self, message: dict[str, Any]) -> None:
        version = _version(message)
        if version <= self._sent_version:
            return
        if self._pending is not None and version < _version(self._pending):
            return
        self._pending = message
        self._wake.set()

    def put_control(self, message: dict[str, Any]) -> None:
        self._control = message
        self._wake.set()

    async def _run(self) -> None:
        try:
            while True:
                await self._wake.wait()
                self._wake.clear()
                control, self._control = self._control, None
                if control is not None:
                    async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
                        await self._ws.send_json(control)
                message, self._pending = self._pending, None
                if message is None:
                    continue
                async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
                    await self._ws.send_json(message)
                self._sent_version = _version(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("dropping stalled or dead socket: %r", exc)
            self._on_dead()
            try:
                async with asyncio.timeout(1):
                    await self._ws.close(code=1011)
            except Exception:
                pass


class RoomHub:
    """Tracks the WebSockets open per room in this process and pushes snapshots to them.

    `publish` never waits on the network: every socket has its own outbox and sender task,
    so one slow or frozen client can't delay anyone else.
    """

    def __init__(self) -> None:
        self._outboxes: dict[str, dict[WebSocket, _Outbox]] = {}

    def has(self, code: str) -> bool:
        return bool(self._outboxes.get(code))

    def rooms(self) -> list[str]:
        return list(self._outboxes)

    def add(self, code: str, ws: WebSocket) -> None:
        room = self._outboxes.setdefault(code, {})
        if ws not in room:
            room[ws] = _Outbox(ws, on_dead=lambda: self.remove(code, ws))

    def remove(self, code: str, ws: WebSocket) -> None:
        room = self._outboxes.get(code)
        if room is None or ws not in room:
            return
        outbox = room.pop(ws)
        if asyncio.current_task() is not outbox.task:
            outbox.task.cancel()
        if not room:
            del self._outboxes[code]

    def send(self, code: str, ws: WebSocket, message: dict[str, Any]) -> None:
        """Queue a message for one socket (e.g. its first snapshot)."""
        outbox = self._outboxes.get(code, {}).get(ws)
        if outbox is not None:
            outbox.put(message)

    def send_control(self, code: str, ws: WebSocket, message: dict[str, Any]) -> None:
        """Queue an unversioned message (e.g. a heartbeat pong) for one socket."""
        outbox = self._outboxes.get(code, {}).get(ws)
        if outbox is not None:
            outbox.put_control(message)

    def publish_control(self, code: str, message: dict[str, Any]) -> None:
        for outbox in self._outboxes.get(code, {}).values():
            outbox.put_control(message)

    def publish(self, code: str, message: dict[str, Any]) -> None:
        for outbox in self._outboxes.get(code, {}).values():
            outbox.put(message)
