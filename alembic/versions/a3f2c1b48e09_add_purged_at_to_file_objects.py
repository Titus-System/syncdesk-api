"""add purged_at to file_objects

Revision ID: a3f2c1b48e09
Revises: dd164affd8d5
Create Date: 2026-05-25 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f2c1b48e09'
down_revision: Union[str, Sequence[str], None] = 'dd164affd8d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotency marker for the physical-purge job. Soft-deleted rows live
    # until ``deleted_at + FILE_RETENTION_GRACE_DAYS``; once the object is
    # removed from MinIO, ``purged_at`` is stamped so subsequent passes
    # skip the row. Additive and nullable to preserve staging data.
    op.add_column(
        'file_objects',
        sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('file_objects', 'purged_at')
