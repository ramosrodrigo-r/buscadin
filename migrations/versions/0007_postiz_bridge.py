"""Queue approved carousel images for private Postiz draft handoff."""

from alembic import op
import sqlalchemy as sa

revision = "0007_postiz_bridge"
down_revision = "0006_carousel_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("carousel_drafts", sa.Column("postiz_assets", sa.JSON()))
    op.add_column("carousel_drafts", sa.Column("postiz_state", sa.String(24)))
    op.add_column("carousel_drafts", sa.Column("postiz_post_id", sa.String(255)))
    op.add_column("carousel_drafts", sa.Column("postiz_error", sa.String(255)))
    op.add_column("carousel_drafts", sa.Column("postiz_claimed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_carousel_postiz_state", "carousel_drafts", ["postiz_state"])


def downgrade() -> None:
    op.drop_index("ix_carousel_postiz_state", table_name="carousel_drafts")
    for name in ("postiz_claimed_at", "postiz_error", "postiz_post_id", "postiz_state", "postiz_assets"):
        op.drop_column("carousel_drafts", name)
