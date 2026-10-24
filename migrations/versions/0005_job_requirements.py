"""Record explicit requirement evidence and searchable approved content."""

from alembic import op
import sqlalchemy as sa

revision = "0005_job_requirements"
down_revision = "0004_site_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("requirements", sa.JSON(), nullable=False, server_default="{}"))
    with op.batch_alter_table("site_publications") as batch:
        batch.add_column(sa.Column("search_text", sa.Text(), nullable=False, server_default=""))
    # Existing approved content remains approved; only derive a search index.
    import json
    import unicodedata

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT job_id, public_snapshot FROM site_publications")).mappings()
    for row in rows:
        snapshot = row["public_snapshot"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        content = " ".join(str(snapshot.get(key) or "") for key in ("title", "company", "summary"))
        normalized = " ".join("".join(character for character in unicodedata.normalize("NFKD", content.casefold()) if not unicodedata.combining(character)).split())
        connection.execute(sa.text("UPDATE site_publications SET search_text = :search WHERE job_id = :id"), {"search": normalized, "id": row["job_id"]})


def downgrade() -> None:
    with op.batch_alter_table("site_publications") as batch:
        batch.drop_column("search_text")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("requirements")
