"""Add optional expected domains for referral URL validation."""

from alembic import op
import sqlalchemy as sa


revision = "0003_referral_domains"
down_revision = "0002_indications_editorial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("referral_programs") as batch:
        batch.add_column(
            sa.Column("allowed_domains", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("referral_programs") as batch:
        batch.drop_column("allowed_domains")
