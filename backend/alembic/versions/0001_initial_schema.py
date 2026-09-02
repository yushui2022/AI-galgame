"""Initial AI Galgame schema.

Revision ID: 0001
Revises:
"""

from alembic import op
from app import models  # noqa: F401
from app.database import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            memory_id UNINDEXED,
            game_id UNINDEXED,
            content,
            tags
        )
        """
    )


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute("DROP TABLE IF EXISTS memory_fts")
    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("PRAGMA foreign_keys=ON")
