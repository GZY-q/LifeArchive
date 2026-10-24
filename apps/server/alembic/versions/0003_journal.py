"""Preserve private journal originals and immutable revision snapshots."""

import sqlalchemy as sa
from alembic import op

revision: str = "0003_journal"
down_revision: str | None = "0002_owner_sessions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_timezone", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("revision > 0", name=op.f("ck_entries_positive_revision")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_entries_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entries")),
        sa.UniqueConstraint(
            "user_id", "client_request_id", name=op.f("uq_entries_user_id_client_request_id")
        ),
    )
    op.create_index(
        "ix_entries_owner_date_created_id",
        "entries",
        ["user_id", sa.text("entry_date DESC"), sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_table(
        "entry_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("editor_id", sa.Uuid(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision > 0", name=op.f("ck_entry_revisions_positive_revision")),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entries.id"], name=op.f("fk_entry_revisions_entry_id_entries")
        ),
        sa.ForeignKeyConstraint(
            ["editor_id"], ["users.id"], name=op.f("fk_entry_revisions_editor_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entry_revisions")),
        sa.UniqueConstraint(
            "entry_id", "revision", name=op.f("uq_entry_revisions_entry_id_revision")
        ),
    )


def downgrade() -> None:
    op.drop_table("entry_revisions")
    op.drop_index("ix_entries_owner_date_created_id", table_name="entries")
    op.drop_table("entries")
