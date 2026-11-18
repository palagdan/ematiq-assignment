from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Currency(StrEnum):
    CZK = "CZK"
    EUR = "EUR"
    BTC = "BTC"


class RoomStatus(StrEnum):
    LOBBY = "lobby"
    PLAYING = "playing"
    FINISHED = "finished"


class FinishReason(StrEnum):
    BOMB = "bomb"
    GAVE_UP = "gave_up"
    TIMEOUT = "timeout"


def _enum_values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    # Stored lowercase. Optional for accounts created before emails were required.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # sha256 of the opaque token; the raw token only ever lives in the cookie.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]

    user: Mapped[User] = relationship(lazy="joined")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    # sha256 of the token from the emailed link.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(6), unique=True)
    # Game records are immutable history: users referenced by them can't be hard-deleted
    # (RESTRICT), only anonymised, so a deletion can never rewrite who played or paid.
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, name="room_status", values_callable=_enum_values),
        default=RoomStatus.LOBBY,
        index=True,
    )
    grid_size: Mapped[int] = mapped_column(default=9)
    # Number of safe cells opened so far; the player on turn is seat turn_index % players.
    turn_index: Mapped[int] = mapped_column(default=0)
    # Chosen by the host; the player on turn must move before `turn_deadline` or they pay.
    turn_seconds: Mapped[int] = mapped_column(default=60, server_default="60")
    turn_deadline: Mapped[datetime | None] = mapped_column(index=True)
    bomb_commitment: Mapped[str | None] = mapped_column(String(64))
    bomb_index: Mapped[int | None]
    bomb_salt: Mapped[str | None] = mapped_column(String(64))
    loser_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    finish_reason: Mapped[FinishReason | None] = mapped_column(
        Enum(FinishReason, name="finish_reason", values_callable=_enum_values)
    )
    # CZK price of one unit of each currency, frozen when the game finished.
    rates_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None] = mapped_column(index=True)
    # Bumped by every change; idle lobbies expire based on it.
    last_activity_at: Mapped[datetime] = mapped_column(server_default=func.now())

    players: Mapped[list["RoomPlayer"]] = relationship(
        back_populates="room",
        order_by="RoomPlayer.joined_at",
        cascade="all, delete-orphan",
    )
    moves: Mapped[list["Move"]] = relationship(order_by="Move.id", cascade="all, delete-orphan")


class RoomPlayer(Base):
    __tablename__ = "room_players"

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    # Assigned (shuffled) when the game starts.
    seat: Mapped[int | None]
    meal_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    meal_currency: Mapped[Currency | None] = mapped_column(
        Enum(Currency, name="currency", values_callable=_enum_values)
    )
    joined_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())

    room: Mapped[Room] = relationship(back_populates="players")
    user: Mapped[User] = relationship(lazy="joined")


class Move(Base):
    __tablename__ = "moves"
    __table_args__ = (UniqueConstraint("room_id", "cell_index"),)
    # Fetch server defaults (created_at) with the INSERT: a move can be returned without a reload.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    cell_index: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RateLimitHit(Base):
    """Fixed-window request counters, shared by every worker and replica."""

    __tablename__ = "rate_limits"

    # "<rule>:<sha256 of the subject>", so no usernames, emails or IPs are stored in clear.
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(primary_key=True, index=True)
    hits: Mapped[int] = mapped_column(default=1)
