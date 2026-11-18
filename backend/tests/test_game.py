import pytest

from lunch.errors import Conflict, DomainError
from lunch.rooms import game


def test_commitment_matches_placed_bomb() -> None:
    bomb = game.place_bomb(16)
    assert 0 <= bomb.index < 16
    assert game.commitment(bomb.index, bomb.salt) == bomb.commitment
    assert game.commitment(bomb.index + 1, bomb.salt) != bomb.commitment


def test_room_code_alphabet() -> None:
    code = game.new_room_code()
    assert len(code) == game.CODE_LENGTH
    assert set(code) <= set(game.CODE_ALPHABET)
    assert game.normalize_code(f"  {code.lower()} ") == code


def test_turns_rotate_through_seats() -> None:
    assert [game.seat_on_turn(t, 3) for t in range(7)] == [0, 1, 2, 0, 1, 2, 0]


def test_shuffle_keeps_all_players() -> None:
    assert sorted(game.shuffle_seats([1, 2, 3, 4])) == [1, 2, 3, 4]


@pytest.mark.parametrize(
    ("grid", "players"),
    [(game.MIN_GRID - 1, 2), (game.MAX_GRID + 1, 2), (5, 5)],
)
def test_invalid_grid_size(grid: int, players: int) -> None:
    with pytest.raises(DomainError):
        game.check_grid_size(grid, players)


def test_cannot_start_alone_or_without_meals() -> None:
    with pytest.raises(Conflict):
        game.check_can_start(player_count=1, grid_size=9, all_meals_set=True)
    with pytest.raises(Conflict):
        game.check_can_start(player_count=3, grid_size=9, all_meals_set=False)
    game.check_can_start(player_count=3, grid_size=9, all_meals_set=True)


def _move(**overrides: object) -> None:
    args: dict[str, object] = {
        "actor_seat": 1,
        "turn_index": 4,
        "player_count": 3,
        "grid_size": 9,
        "opened": {0, 1, 2, 3},
        "cell": 5,
    }
    args.update(overrides)
    game.check_move(**args)  # type: ignore[arg-type]


def test_valid_move() -> None:
    _move()


def test_move_out_of_turn() -> None:
    with pytest.raises(Conflict, match="not your turn"):
        _move(actor_seat=0)


def test_move_outside_grid() -> None:
    with pytest.raises(DomainError, match="outside"):
        _move(cell=9)


def test_move_on_open_cell() -> None:
    with pytest.raises(Conflict, match="already open"):
        _move(cell=2)
