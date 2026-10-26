"""Add private immutable originals and owner-scoped journal image snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_private_images"
down_revision: str | None = "0004_entry_tags"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mime_type", sa.String(32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_assets_user_id_users"),
        sa.UniqueConstraint("user_id", "sha256", name="uq_assets_user_id_sha256"),
        sa.UniqueConstraint("id", "user_id", name="uq_assets_id_user_id"),
        sa.UniqueConstraint("storage_key", name="uq_assets_storage_key"),
        sa.CheckConstraint(
            "byte_size > 0 AND byte_size <= 5242880", name="ck_assets_bounded_bytes"
        ),
        sa.CheckConstraint(
            "width > 0 AND height > 0 AND width <= 20000 AND height <= 20000 "
            "AND CAST(width AS BIGINT) * height <= 20000000",
            name="ck_assets_bounded_pixels",
        ),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_assets_raster_mime",
        ),
    )
    op.create_table(
        "entry_assets",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("entry_id", "asset_id", name="pk_entry_assets"),
        sa.ForeignKeyConstraint(
            ["entry_id", "user_id"],
            ["entries.id", "entries.user_id"],
            name="fk_entry_assets_entry_owner",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id", "user_id"],
            ["assets.id", "assets.user_id"],
            name="fk_entry_assets_asset_owner",
        ),
    )
    op.create_index(
        "ix_entry_assets_owner_asset_entry", "entry_assets", ["user_id", "asset_id", "entry_id"]
    )
    op.add_column(
        "entry_revisions",
        sa.Column(
            "assets", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("entry_revisions", "assets")
    op.drop_table("entry_assets")
    op.drop_table("assets")
