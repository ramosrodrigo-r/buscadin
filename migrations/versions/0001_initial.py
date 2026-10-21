"""Initial Buscadin domain schema."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("application_url", sa.String(length=2048), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("employment_type", sa.String(length=100), nullable=True),
        sa.Column("remote_type", sa.String(length=100), nullable=True),
        sa.Column("eligible_countries", sa.JSON(), nullable=False),
        sa.Column("eligibility_status", sa.String(length=32), nullable=False),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("salary_period", sa.String(length=32), nullable=True),
        sa.Column("salary_disclosed", sa.Boolean(), nullable=False),
        sa.Column("language_requirements", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_job_id", name="uq_jobs_source_source_job_id"),
    )
    op.create_index("ix_jobs_review_status", "jobs", ["review_status"])
    op.create_index("ix_jobs_eligibility_status", "jobs", ["eligibility_status"])
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=True),
        sa.Column("referral_url", sa.String(length=2048), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("approved_for_public_sharing", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referrals_lookup", "referrals", ["company", "source_job_id", "scope"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_notifications_job_id"),
    )
    op.create_table(
        "bot_state",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("bot_state")
    op.drop_table("notifications")
    op.drop_index("ix_referrals_lookup", table_name="referrals")
    op.drop_table("referrals")
    op.drop_index("ix_jobs_eligibility_status", table_name="jobs")
    op.drop_index("ix_jobs_review_status", table_name="jobs")
    op.drop_table("jobs")
