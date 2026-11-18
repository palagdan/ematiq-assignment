from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from lunch.models import Currency, FinishReason, Room, RoomStatus
from lunch.money import parse_rates, totals
from lunch.rooms.game import MAX_GRID, MIN_GRID, seat_on_turn


class MealIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("1000000"), decimal_places=8)
    currency: Currency


class SettingsIn(BaseModel):
    grid_size: int | None = Field(None, ge=MIN_GRID, le=MAX_GRID)
    turn_seconds: int | None = None


class MoveIn(BaseModel):
    cell: int = Field(ge=0)


class RoomCreated(BaseModel):
    code: str


class PlayerOut(BaseModel):
    user_id: int
    username: str
    seat: int | None
    meal_amount: Decimal | None
    meal_currency: Currency | None


class MoveOut(BaseModel):
    user_id: int
    cell: int
    at: datetime


class RoomOut(BaseModel):
    code: str
    status: RoomStatus
    version: int
    host_id: int
    grid_size: int
    players: list[PlayerOut]
    moves: list[MoveOut]
    current_player_id: int | None
    bomb_commitment: str | None
    # Revealed only once the game is finished.
    bomb_index: int | None
    bomb_salt: str | None
    loser_id: int | None
    finish_reason: FinishReason | None
    turn_seconds: int
    turn_deadline: datetime | None
    # Lets clients correct for clock skew when showing the turn countdown.
    server_time: datetime
    rates: dict[Currency, Decimal] | None
    totals: dict[Currency, Decimal] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_room(cls, room: Room) -> "RoomOut":
        finished = room.status is RoomStatus.FINISHED
        players = room.players
        if room.status is not RoomStatus.LOBBY:
            players = sorted(players, key=lambda p: p.seat if p.seat is not None else 0)

        current_player_id = None
        if room.status is RoomStatus.PLAYING:
            seat = seat_on_turn(room.turn_index, len(players))
            current_player_id = next(p.user_id for p in players if p.seat == seat)

        rates = parse_rates(room.rates_snapshot) if room.rates_snapshot else None
        meals = [
            (p.meal_amount, p.meal_currency)
            for p in players
            if p.meal_amount is not None and p.meal_currency is not None
        ]
        return cls(
            code=room.code,
            status=room.status,
            version=room.version,
            host_id=room.host_id,
            grid_size=room.grid_size,
            players=[
                PlayerOut(
                    user_id=p.user_id,
                    username=p.user.username,
                    seat=p.seat,
                    meal_amount=p.meal_amount,
                    meal_currency=p.meal_currency,
                )
                for p in players
            ],
            moves=[
                MoveOut(user_id=m.user_id, cell=m.cell_index, at=m.created_at) for m in room.moves
            ],
            current_player_id=current_player_id,
            bomb_commitment=room.bomb_commitment,
            bomb_index=room.bomb_index if finished else None,
            bomb_salt=room.bomb_salt if finished else None,
            loser_id=room.loser_id,
            finish_reason=room.finish_reason,
            turn_seconds=room.turn_seconds,
            turn_deadline=room.turn_deadline,
            server_time=datetime.now(UTC),
            rates=rates,
            totals=totals(meals, rates) if rates else None,
            created_at=room.created_at,
            started_at=room.started_at,
            finished_at=room.finished_at,
        )
