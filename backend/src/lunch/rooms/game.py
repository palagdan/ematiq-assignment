"""Bomb grid rules. Pure functions with no I/O.

A grid of `grid_size` cells hides one bomb. Players take turns opening cells;
whoever opens the bomb pays for everyone's lunch. When the game starts, the
server publishes sha256("<bomb_index>:<salt>") and reveals both values when
the game ends, so players can check the bomb was never moved.
"""

import hashlib
import secrets
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from random import SystemRandom

from lunch.errors import Conflict, DomainError

MIN_PLAYERS = 2
MAX_PLAYERS = 12
MIN_GRID = 4
MAX_GRID = 64
# Turn lengths the host can pick; there is deliberately no "unlimited" so games can't get stuck.
TURN_SECONDS_OPTIONS = (15, 30, 60, 120, 300)
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6

_random = SystemRandom()


@dataclass(frozen=True)
class Bomb:
    index: int
    salt: str
    commitment: str


def new_room_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(code: str) -> str:
    return code.strip().upper()


def commitment(bomb_index: int, salt: str) -> str:
    return hashlib.sha256(f"{bomb_index}:{salt}".encode()).hexdigest()


def place_bomb(grid_size: int) -> Bomb:
    index = secrets.randbelow(grid_size)
    salt = secrets.token_hex(16)
    return Bomb(index=index, salt=salt, commitment=commitment(index, salt))


def shuffle_seats[T](players: Sequence[T]) -> list[T]:
    order = list(players)
    _random.shuffle(order)
    return order


def seat_on_turn(turn_index: int, player_count: int) -> int:
    return turn_index % player_count


def check_grid_size(grid_size: int, player_count: int) -> None:
    if not MIN_GRID <= grid_size <= MAX_GRID:
        raise DomainError(f"Grid size must be between {MIN_GRID} and {MAX_GRID}")
    if grid_size < player_count + 1:
        raise DomainError("Grid needs at least one cell more than there are players")


def check_turn_seconds(turn_seconds: int) -> None:
    if turn_seconds not in TURN_SECONDS_OPTIONS:
        options = ", ".join(str(s) for s in TURN_SECONDS_OPTIONS)
        raise DomainError(f"Turn time must be one of: {options} seconds")


def check_can_start(player_count: int, grid_size: int, all_meals_set: bool) -> None:
    if player_count < MIN_PLAYERS:
        raise Conflict(f"At least {MIN_PLAYERS} players are needed")
    if not all_meals_set:
        raise Conflict("Every player has to enter their meal price first")
    check_grid_size(grid_size, player_count)


def check_move(
    *,
    actor_seat: int,
    turn_index: int,
    player_count: int,
    grid_size: int,
    opened: Collection[int],
    cell: int,
) -> None:
    if actor_seat != seat_on_turn(turn_index, player_count):
        raise Conflict("It is not your turn")
    if not 0 <= cell < grid_size:
        raise DomainError("Cell is outside of the grid")
    if cell in opened:
        raise Conflict("Cell is already open")
