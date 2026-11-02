"""Persist AI carousel copy requests and reviewed drafts."""

from alembic import op
import sqlalchemy as sa

revision = "0006_carousel_drafts"
down_revision = "0005_job_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "carousel_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("job_ids", sa.JSON(), nullable=False),
        sa.Column("job_snapshot", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("requested_by", sa.String(255), nullable=False, server_default="admin:web"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("post_url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_carousel_drafts_status_created", "carousel_drafts", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_carousel_drafts_status_created", table_name="carousel_drafts")
    op.drop_table("carousel_drafts")
