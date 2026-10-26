"""Store current and historical pin state without changing archive dates."""

import sqlalchemy as sa
from alembic import op

revision: str = "0006_journal_pinning"
down_revision: str | None = "0005_private_images"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table in ("entries", "entry_revisions"):
        op.add_column(
            table,
            sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.create_index(
        "ix_entries_active_owner_pinned_date_created_id",
        "entries",
        [
            "user_id",
            sa.text("is_pinned DESC"),
            sa.text("entry_date DESC"),
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_entries_active_owner_pinned_date_created_id", table_name="entries")
    op.drop_column("entry_revisions", "is_pinned")
    op.drop_column("entries", "is_pinned")
