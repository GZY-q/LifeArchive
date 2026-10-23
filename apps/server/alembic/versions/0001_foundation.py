"""Establish the migration chain without creating future business tables."""

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Alembic records this revision in its own alembic_version table."""


def downgrade() -> None:
    """No application schema exists at this baseline."""
