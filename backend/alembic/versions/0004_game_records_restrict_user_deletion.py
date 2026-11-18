"""game records restrict user deletion

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18 14:34:18.096015
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column, ON DELETE before) for every game-record reference to a user.
FOREIGN_KEYS = [
    ("moves", "user_id", None),
    ("room_players", "user_id", "CASCADE"),
    ("rooms", "host_id", None),
    ("rooms", "loser_id", None),
]


def _replace(table: str, column: str, ondelete: str | None) -> None:
    name = f"{table}_{column}_fkey"
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(name, table, "users", [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    # Game records are immutable history: block hard-deleting users they reference.
    for table, column, _ in FOREIGN_KEYS:
        _replace(table, column, "RESTRICT")


def downgrade() -> None:
    for table, column, previous in FOREIGN_KEYS:
        _replace(table, column, previous)
