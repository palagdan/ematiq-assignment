"""Room commands.

Each command runs in one transaction that locks the room row
(SELECT ... FOR UPDATE), so concurrent actions in the same room are
serialized and turn checks can't race. Every change bumps `room.version`,
which clients use to drop stale WebSocket snapshots.

A player can be in only one active (lobby or playing) room at a time. Creating
and joining also lock the user's row, so two tabs can't race past that check.
Lock order is always room first, then user.

So nobody gets stuck: the host can remove absent players from the lobby, idle lobbies
expire, and a running game has a turn timer. Whoever lets it run out pays.

Commands return the committed room. Server defaults come back with the INSERT, and new
rows get their relationships set in memory, so there's no need to reload it.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lunch.errors import Conflict, DomainError, Forbidden, NotFound
from lunch.models import Currency, FinishReason, Move, Room, RoomPlayer, RoomStatus, User
from lunch.money import serialize_rates
from lunch.rooms import game

_LOAD_OPTIONS = (
    selectinload(Room.players).joinedload(RoomPlayer.user),
    selectinload(Room.moves),
)


async def load_room(db: AsyncSession, code: str, *, for_update: bool = False) -> Room:
    stmt = (
        select(Room)
        .where(Room.code == game.normalize_code(code))
        .options(*_LOAD_OPTIONS)
        .execution_options(populate_existing=True)
    )
    if for_update:
        stmt = stmt.with_for_update(of=Room)
    room = await db.scalar(stmt)
    if room is None:
        raise NotFound("Room not found")
    return room


def _member(room: Room, user: User) -> RoomPlayer:
    for player in room.players:
        if player.user_id == user.id:
            return player
    raise Forbidden("You are not a player in this room")


def _require_status(room: Room, status: RoomStatus) -> None:
    if room.status is not status:
        messages = {
            RoomStatus.LOBBY: "The game has already started",
            RoomStatus.PLAYING: "The game is not running",
            RoomStatus.FINISHED: "The game is not finished",
        }
        raise Conflict(messages[status])


# Postgres channel announcing "room <code> changed" to every backend process (see events.py).
ROOM_EVENTS_CHANNEL = "room_events"


def _now() -> datetime:
    return datetime.now(UTC)


async def _commit(db: AsyncSession, room: Room) -> Room:
    room.version += 1
    room.last_activity_at = _now()
    # Sent inside the transaction: delivered only if it commits, in commit order.
    await db.execute(select(func.pg_notify(ROOM_EVENTS_CHANNEL, room.code)))
    await db.commit()
    return room


ACTIVE_STATUSES = (RoomStatus.LOBBY, RoomStatus.PLAYING)


async def current_room_code(db: AsyncSession, user_id: int) -> str | None:
    """The code of the active room the user is in, if any."""
    return await db.scalar(
        select(Room.code)
        .join(RoomPlayer)
        .where(RoomPlayer.user_id == user_id, Room.status.in_(ACTIVE_STATUSES))
        # Normally there is at most one; prefer a running game, then the newest lobby.
        .order_by((Room.status == RoomStatus.PLAYING).desc(), Room.created_at.desc())
        .limit(1)
    )


async def _ensure_free(db: AsyncSession, user_id: int) -> None:
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    active = await current_room_code(db, user_id)
    if active is not None:
        raise Conflict(f"You are already in room {active}. Finish or leave it first.")


async def create_room(db: AsyncSession, user: User) -> str:
    # Read once: a rollback below expires `user`, and reloading it lazily isn't allowed in async.
    user_id = user.id
    for _ in range(10):
        await _ensure_free(db, user_id)
        room = Room(code=game.new_room_code(), host_id=user_id, status=RoomStatus.LOBBY)
        room.players.append(RoomPlayer(user_id=user_id))
        db.add(room)
        try:
            await db.commit()
        except IntegrityError:  # code collision, try another one
            await db.rollback()
            continue
        return room.code
    raise Conflict("Could not allocate a room code, try again")


async def join_room(db: AsyncSession, user: User, code: str) -> Room:
    room = await load_room(db, code, for_update=True)
    if any(p.user_id == user.id for p in room.players):
        await db.commit()  # already in: nothing to change, just release the lock
        return room
    _require_status(room, RoomStatus.LOBBY)
    if len(room.players) >= game.MAX_PLAYERS:
        raise Conflict("The room is full")
    await _ensure_free(db, user.id)
    room.players.append(RoomPlayer(user_id=user.id, user=user, joined_at=_now()))
    return await _commit(db, room)


def _drop_player(room: Room, player: RoomPlayer) -> None:
    room.players.remove(player)
    if room.host_id == player.user_id and room.players:
        room.host_id = room.players[0].user_id


async def leave_room(db: AsyncSession, user: User, code: str) -> Room | None:
    """Returns None if the room was deleted because its last player left."""
    room = await load_room(db, code, for_update=True)
    player = _member(room, user)
    _require_status(room, RoomStatus.LOBBY)
    _drop_player(room, player)
    if not room.players:
        await db.delete(room)
        await db.commit()
        return None
    return await _commit(db, room)


async def remove_player(db: AsyncSession, host: User, code: str, user_id: int) -> Room:
    """The host removes someone from the lobby (e.g. they walked away without leaving)."""
    room = await load_room(db, code, for_update=True)
    if room.host_id != host.id:
        raise Forbidden("Only the host can remove players")
    _require_status(room, RoomStatus.LOBBY)
    if user_id == host.id:
        raise DomainError("Use Leave to leave your own room")
    player = next((p for p in room.players if p.user_id == user_id), None)
    if player is None:
        raise NotFound("That player is not in this room")
    _drop_player(room, player)
    return await _commit(db, room)


async def set_meal(
    db: AsyncSession, user: User, code: str, amount: Decimal, currency: Currency
) -> Room:
    room = await load_room(db, code, for_update=True)
    player = _member(room, user)
    _require_status(room, RoomStatus.LOBBY)
    player.meal_amount = amount
    player.meal_currency = currency
    return await _commit(db, room)


async def update_settings(
    db: AsyncSession, user: User, code: str, grid_size: int | None, turn_seconds: int | None
) -> Room:
    room = await load_room(db, code, for_update=True)
    if room.host_id != user.id:
        raise Forbidden("Only the host can change the settings")
    _require_status(room, RoomStatus.LOBBY)
    if grid_size is not None:
        game.check_grid_size(grid_size, len(room.players))
        room.grid_size = grid_size
    if turn_seconds is not None:
        game.check_turn_seconds(turn_seconds)
        room.turn_seconds = turn_seconds
    return await _commit(db, room)


async def start_game(db: AsyncSession, user: User, code: str) -> Room:
    room = await load_room(db, code, for_update=True)
    if room.host_id != user.id:
        raise Forbidden("Only the host can start the game")
    _require_status(room, RoomStatus.LOBBY)
    game.check_can_start(
        player_count=len(room.players),
        grid_size=room.grid_size,
        all_meals_set=all(p.meal_amount is not None for p in room.players),
    )
    for seat, player in enumerate(game.shuffle_seats(room.players)):
        player.seat = seat
    bomb = game.place_bomb(room.grid_size)
    room.bomb_index = bomb.index
    room.bomb_salt = bomb.salt
    room.bomb_commitment = bomb.commitment
    room.turn_index = 0
    room.status = RoomStatus.PLAYING
    room.started_at = _now()
    _start_turn(room)
    return await _commit(db, room)


def _start_turn(room: Room) -> None:
    room.turn_deadline = _now() + timedelta(seconds=room.turn_seconds)


async def open_cell(
    db: AsyncSession, user: User, code: str, cell: int, rates: dict[Currency, Decimal]
) -> Room:
    """Rates are passed in so no network call happens while the row is locked."""
    room = await load_room(db, code, for_update=True)
    player = _member(room, user)
    _require_status(room, RoomStatus.PLAYING)
    assert player.seat is not None
    game.check_move(
        actor_seat=player.seat,
        turn_index=room.turn_index,
        player_count=len(room.players),
        grid_size=room.grid_size,
        opened={m.cell_index for m in room.moves},
        cell=cell,
    )
    room.moves.append(Move(room_id=room.id, user_id=user.id, cell_index=cell))
    if cell == room.bomb_index:
        _finish(room, user.id, rates, FinishReason.BOMB)
    else:
        room.turn_index += 1
        _start_turn(room)
    return await _commit(db, room)


async def give_up(db: AsyncSession, user: User, code: str, rates: dict[Currency, Decimal]) -> Room:
    """Leaving a running game means losing it: the quitter pays."""
    room = await load_room(db, code, for_update=True)
    _member(room, user)
    _require_status(room, RoomStatus.PLAYING)
    _finish(room, user.id, rates, FinishReason.GAVE_UP)
    return await _commit(db, room)


async def expired_turn_codes(db: AsyncSession) -> list[str]:
    stmt = select(Room.code).where(
        Room.status == RoomStatus.PLAYING, Room.turn_deadline <= func.now()
    )
    return list(await db.scalars(stmt))


async def expire_turn(db: AsyncSession, code: str, rates: dict[Currency, Decimal]) -> Room | None:
    """If the player on turn ran out of time, they lose and pay. Safe to call from several
    workers at once: the row lock serializes them and the deadline is re-checked under it."""
    room = await load_room(db, code, for_update=True)
    if (
        room.status is not RoomStatus.PLAYING
        or room.turn_deadline is None
        or room.turn_deadline > _now()
    ):
        await db.commit()
        return None
    seat = game.seat_on_turn(room.turn_index, len(room.players))
    loser = next(p for p in room.players if p.seat == seat)
    _finish(room, loser.user_id, rates, FinishReason.TIMEOUT)
    return await _commit(db, room)


async def expire_idle_lobbies(db: AsyncSession, idle_for: timedelta) -> list[str]:
    """Delete lobbies nobody touched for `idle_for`, freeing their players."""
    codes = list(
        await db.scalars(
            delete(Room)
            .where(Room.status == RoomStatus.LOBBY, Room.last_activity_at < _now() - idle_for)
            .returning(Room.code)
        )
    )
    for code in codes:  # open pages learn the room is gone
        await db.execute(select(func.pg_notify(ROOM_EVENTS_CHANNEL, code)))
    await db.commit()
    return codes


def _finish(
    room: Room, loser_id: int, rates: dict[Currency, Decimal], reason: FinishReason
) -> None:
    room.status = RoomStatus.FINISHED
    room.loser_id = loser_id
    room.finish_reason = reason
    room.finished_at = _now()
    room.turn_deadline = None
    room.rates_snapshot = serialize_rates(rates)
