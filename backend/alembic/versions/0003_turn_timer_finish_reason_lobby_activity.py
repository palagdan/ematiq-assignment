"""turn timer, finish reason, lobby activity

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 14:26:13.944055
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FINISH_REASON = sa.Enum("bomb", "gave_up", "timeout", name="finish_reason")


def upgrade() -> None:
    FINISH_REASON.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "rooms", sa.Column("turn_seconds", sa.Integer(), server_default="60", nullable=False)
    )
    op.add_column("rooms", sa.Column("turn_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rooms", sa.Column("finish_reason", FINISH_REASON, nullable=True))
    op.add_column(
        "rooms",
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_rooms_turn_deadline"), "rooms", ["turn_deadline"], unique=False)

    # Past games: a bomb move means the bomb ended it; otherwise someone gave up.
    op.execute(
        """
        UPDATE rooms r SET finish_reason = CASE
            WHEN EXISTS (
                SELECT 1 FROM moves m WHERE m.room_id = r.id AND m.cell_index = r.bomb_index
            ) THEN 'bomb'::finish_reason
            ELSE 'gave_up'::finish_reason
        END
        WHERE r.status = 'finished'
        """
    )
    op.execute("UPDATE rooms SET last_activity_at = coalesce(finished_at, started_at, created_at)")
    # Games already running get a fresh turn timer.
    op.execute(
        "UPDATE rooms SET turn_deadline = now() + make_interval(secs => turn_seconds)"
        " WHERE status = 'playing'"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rooms_turn_deadline"), table_name="rooms")
    op.drop_column("rooms", "last_activity_at")
    op.drop_column("rooms", "finish_reason")
    op.drop_column("rooms", "turn_deadline")
    op.drop_column("rooms", "turn_seconds")
    FINISH_REASON.drop(op.get_bind(), checkfirst=True)
