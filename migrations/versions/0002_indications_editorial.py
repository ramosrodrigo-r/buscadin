"""Add referral programs, editorial workflow and audit history."""

from alembic import op
import sqlalchemy as sa


revision = "0002_indications_editorial"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_programs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("campaign_key", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("public_sharing_allowed", sa.Boolean(), nullable=True),
        sa.Column("evidence_url", sa.String(length=2048), nullable=True),
        sa.Column("rules_notes", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_referral_programs_company_active",
        "referral_programs",
        ["company", "is_active"],
    )
    op.create_table(
        "referral_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("campaign_key", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("verified_by", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["referral_programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referral_links_program_active", "referral_links", ["program_id", "is_active"])
    op.create_index("ix_referral_links_job", "referral_links", ["job_id"])
    op.create_table(
        "editorial_publications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("post_url", sa.String(length=2048), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_job_created", "audit_events", ["job_id", "created_at"])

    with op.batch_alter_table("jobs") as batch:
        batch.add_column(
            sa.Column("referral_status", sa.String(length=32), nullable=False, server_default="SEM_PROGRAMA")
        )
        batch.add_column(sa.Column("referral_status_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("resolved_referral_link_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("referral_campaign_key", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("editorial_status", sa.String(length=32), nullable=False, server_default="NOVA"))
        batch.add_column(sa.Column("editorial_updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_jobs_referral_status", ["referral_status"])
        batch.create_index("ix_jobs_editorial_status", ["editorial_status"])
        batch.create_foreign_key(
            "fk_jobs_resolved_referral_link_id",
            "referral_links",
            ["resolved_referral_link_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("last_notified_referral_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("last_notified_referral_status")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("fk_jobs_resolved_referral_link_id", type_="foreignkey")
        batch.drop_index("ix_jobs_editorial_status")
        batch.drop_index("ix_jobs_referral_status")
        batch.drop_column("editorial_updated_at")
        batch.drop_column("editorial_status")
        batch.drop_column("referral_campaign_key")
        batch.drop_column("resolved_referral_link_id")
        batch.drop_column("referral_status_reason")
        batch.drop_column("referral_status")
    op.drop_index("ix_audit_events_job_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("editorial_publications")
    op.drop_index("ix_referral_links_job", table_name="referral_links")
    op.drop_index("ix_referral_links_program_active", table_name="referral_links")
    op.drop_table("referral_links")
    op.drop_index("ix_referral_programs_company_active", table_name="referral_programs")
    op.drop_table("referral_programs")
