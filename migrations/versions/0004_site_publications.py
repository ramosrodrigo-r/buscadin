"""Add isolated site snapshots, previews, audit trail and administrator alerts.

No existing job or editorial status is migrated to a public state.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_site_publications"
down_revision = "0003_referral_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_publications",
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("public_snapshot", sa.JSON(), nullable=False),
        sa.Column("destination_snapshot", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("unpublished_at", sa.DateTime(timezone=True)),
        sa.Column("application_suspended", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_site_publications_status_date", "site_publications", ["status", "published_at"])
    op.create_table(
        "site_previews",
        sa.Column("token", sa.String(32), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "site_publication_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_key", sa.String(128), unique=True, nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_site_events_job_version", "site_publication_events", ["job_id", "version"])
    op.create_table(
        "site_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_key", sa.String(128), unique=True, nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    # Export/backup these tables before downgrade: publication history is data.
    op.drop_table("site_alerts")
    op.drop_index("ix_site_events_job_version", table_name="site_publication_events")
    op.drop_table("site_publication_events")
    op.drop_table("site_previews")
    op.drop_index("ix_site_publications_status_date", table_name="site_publications")
    op.drop_table("site_publications")
