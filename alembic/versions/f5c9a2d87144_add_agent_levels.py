"""add agent levels

Revision ID: f5c9a2d87144
Revises: a3f2c1b48e09
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5c9a2d87144"
down_revision: Union[str, Sequence[str], None] = "a3f2c1b48e09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "levels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_levels")),
        sa.UniqueConstraint("name", name=op.f("uq_levels_name")),
    )
    op.create_table(
        "user_levels",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["level_id"],
            ["levels.id"],
            name=op.f("fk_user_levels_level_id_levels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_levels_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "level_id", name=op.f("pk_user_levels")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user_levels")
    op.drop_table("levels")
