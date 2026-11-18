import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from lunch.auth.deps import CurrentUser, DbSession
from lunch.models import Currency, FinishReason, Room, RoomPlayer, RoomStatus
from lunch.money import parse_rates, totals

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/history", tags=["history"])

UNKNOWN_PLAYER = "unknown player"


class HistoryPlayer(BaseModel):
    user_id: int
    username: str
    meal_amount: Decimal
    meal_currency: Currency
    paid: bool


class HistoryEntry(BaseModel):
    code: str
    started_at: datetime
    finished_at: datetime
    players: list[HistoryPlayer]
    loser_id: int
    loser_username: str
    finish_reason: FinishReason
    totals: dict[Currency, Decimal]
    rates: dict[Currency, Decimal]


class HistoryPage(BaseModel):
    items: list[HistoryEntry]
    has_more: bool


def _entry(room: Room) -> HistoryEntry:
    assert room.started_at and room.finished_at and room.loser_id and room.rates_snapshot
    players = [
        HistoryPlayer(
            user_id=p.user_id,
            username=p.user.username,
            meal_amount=p.meal_amount,
            meal_currency=p.meal_currency,
            paid=p.user_id == room.loser_id,
        )
        for p in sorted(room.players, key=lambda p: p.seat or 0)
        if p.meal_amount is not None and p.meal_currency is not None
    ]
    rates = parse_rates(room.rates_snapshot)
    # The payer is looked up among all players (not only those with a meal), and a broken
    # record is labelled and logged rather than taking the whole history page down.
    loser = next((p for p in room.players if p.user_id == room.loser_id), None)
    if loser is None:
        log.warning("finished room %s has no player row for loser %s", room.code, room.loser_id)
    return HistoryEntry(
        code=room.code,
        started_at=room.started_at,
        finished_at=room.finished_at,
        players=players,
        loser_id=room.loser_id,
        loser_username=loser.user.username if loser else UNKNOWN_PLAYER,
        finish_reason=room.finish_reason or FinishReason.BOMB,
        totals=totals(((p.meal_amount, p.meal_currency) for p in players), rates),
        rates=rates,
    )


@router.get("")
async def list_history(
    user: CurrentUser,
    db: DbSession,
    mine: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HistoryPage:
    stmt = (
        select(Room)
        .where(Room.status == RoomStatus.FINISHED)
        .options(selectinload(Room.players).joinedload(RoomPlayer.user))
        .order_by(Room.finished_at.desc(), Room.id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    if mine:
        stmt = stmt.where(
            Room.id.in_(select(RoomPlayer.room_id).where(RoomPlayer.user_id == user.id))
        )
    rooms = list(await db.scalars(stmt))
    return HistoryPage(items=[_entry(r) for r in rooms[:limit]], has_more=len(rooms) > limit)
