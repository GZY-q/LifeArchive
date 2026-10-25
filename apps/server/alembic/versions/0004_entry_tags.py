"""Add owner-scoped tags and immutable revision label snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_entry_tags"
down_revision: str | None = "0003_journal"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_entries_id_user_id", "entries", ["id", "user_id"])
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("name_key", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_tags_user_id_users"),
        sa.UniqueConstraint("user_id", "name_key", name="uq_tags_user_id_name_key"),
        sa.UniqueConstraint("id", "user_id", name="uq_tags_id_user_id"),
    )
    op.create_table(
        "entry_tags",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("entry_id", "tag_id", name="pk_entry_tags"),
        sa.ForeignKeyConstraint(
            ["entry_id", "user_id"],
            ["entries.id", "entries.user_id"],
            name="fk_entry_tags_entry_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id", "user_id"],
            ["tags.id", "tags.user_id"],
            name="fk_entry_tags_tag_owner",
        ),
    )
    op.create_index(
        "ix_entry_tags_owner_tag_entry", "entry_tags", ["user_id", "tag_id", "entry_id"]
    )
    op.add_column(
        "entry_revisions",
        sa.Column(
            "tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("entry_revisions", "tags")
    op.drop_table("entry_tags")
    op.drop_table("tags")
    op.drop_constraint("uq_entries_id_user_id", "entries", type_="unique")
