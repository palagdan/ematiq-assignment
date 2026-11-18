from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response, WebSocket, WebSocketDisconnect, status

from lunch import ratelimit
from lunch.auth.deps import SESSION_COOKIE, CurrentUser, DbSession
from lunch.auth.service import user_from_token
from lunch.db import SessionLocal
from lunch.errors import NotFound
from lunch.rates_client import RatesProvider
from lunch.rooms import service
from lunch.rooms.events import state_message
from lunch.rooms.game import normalize_code
from lunch.rooms.hub import RoomHub
from lunch.rooms.schemas import MealIn, MoveIn, RoomCreated, RoomOut, SettingsIn

router = APIRouter(prefix="/api/rooms", tags=["rooms"])
ws_router = APIRouter()


def get_rates(request: Request) -> RatesProvider:
    return cast(RatesProvider, request.app.state.rates)


Rates = Annotated[RatesProvider, Depends(get_rates)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room(user: CurrentUser, db: DbSession) -> RoomCreated:
    await ratelimit.enforce((ratelimit.ROOM_CREATE_PER_USER, str(user.id)))
    return RoomCreated(code=await service.create_room(db, user))


@router.get("/current")
async def current_room(user: CurrentUser, db: DbSession) -> RoomOut | None:
    """The active room the user is in. Declared before /{code} so it isn't taken for a code."""
    code = await service.current_room_code(db, user.id)
    return RoomOut.from_room(await service.load_room(db, code)) if code else None


@router.get("/{code}")
async def get_room(code: str, user: CurrentUser, db: DbSession) -> RoomOut:
    return RoomOut.from_room(await service.load_room(db, code))


@router.post("/{code}/join")
async def join_room(code: str, user: CurrentUser, db: DbSession) -> RoomOut:
    return RoomOut.from_room(await service.join_room(db, user, code))


@router.post("/{code}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_room(code: str, user: CurrentUser, db: DbSession) -> Response:
    await service.leave_room(db, user, code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{code}/players/{user_id}")
async def remove_player(code: str, user_id: int, user: CurrentUser, db: DbSession) -> RoomOut:
    """The host removes a player from the lobby."""
    return RoomOut.from_room(await service.remove_player(db, user, code, user_id))


@router.put("/{code}/meal")
async def set_meal(code: str, body: MealIn, user: CurrentUser, db: DbSession) -> RoomOut:
    return RoomOut.from_room(await service.set_meal(db, user, code, body.amount, body.currency))


@router.patch("/{code}")
async def update_settings(code: str, body: SettingsIn, user: CurrentUser, db: DbSession) -> RoomOut:
    return RoomOut.from_room(
        await service.update_settings(db, user, code, body.grid_size, body.turn_seconds)
    )


@router.post("/{code}/start")
async def start_game(code: str, user: CurrentUser, db: DbSession) -> RoomOut:
    return RoomOut.from_room(await service.start_game(db, user, code))


@router.post("/{code}/moves")
async def open_cell(
    code: str, body: MoveIn, user: CurrentUser, db: DbSession, rates: Rates
) -> RoomOut:
    current_rates = await rates.get_rates()
    return RoomOut.from_room(await service.open_cell(db, user, code, body.cell, current_rates))


@router.post("/{code}/give-up")
async def give_up(code: str, user: CurrentUser, db: DbSession, rates: Rates) -> RoomOut:
    current_rates = await rates.get_rates()
    return RoomOut.from_room(await service.give_up(db, user, code, current_rates))


@ws_router.websocket("/ws/rooms/{code}")
async def room_socket(ws: WebSocket, code: str) -> None:
    """Push-only channel: sends the current snapshot, then every change.

    The DB session is closed before the long-lived loop, so open sockets
    don't hold connections.
    """
    code = normalize_code(code)
    token = ws.cookies.get(SESSION_COOKIE)
    async with SessionLocal() as db:
        user = await user_from_token(db, token) if token else None
        if user is None:
            await ws.close(code=4401, reason="Not logged in")
            return
        try:
            await service.load_room(db, code)
        except NotFound:
            await ws.close(code=4404, reason="Room not found")
            return

    hub = cast(RoomHub, ws.app.state.hub)
    await ws.accept()
    # Register before reading the snapshot so no change committed in between is lost.
    hub.add(code, ws)
    try:
        async with SessionLocal() as db:
            room = RoomOut.from_room(await service.load_room(db, code))
        hub.send(code, ws, state_message(room))
        while True:
            # App-level heartbeat: browsers can't see protocol pings, so the client sends "ping"
            # and treats a missing "pong" as a dead connection. Server-side, uvicorn's protocol
            # pings (--ws-ping-interval/--ws-ping-timeout) drop clients that vanish silently.
            if await ws.receive_text() == "ping":
                hub.send_control(code, ws, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(code, ws)
