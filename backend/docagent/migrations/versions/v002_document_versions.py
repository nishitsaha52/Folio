"""Register only successfully committed artifact versions.

Revision ID: 002
Revises: 001
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_versions",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("baseline_hash", sa.String(64), nullable=False),
        sa.Column("package_sha256", sa.String(64), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
    )
    # Only a completed job's latest version is provably committed in the old schema.
    # Its legacy package checksum is unknown, rather than invented.
    jobs = sa.table(
        "jobs",
        sa.column("id"),
        sa.column("version"),
        sa.column("baseline_hash"),
        sa.column("created"),
        sa.column("status"),
    )
    versions = sa.table(
        "document_versions",
        sa.column("job_id"),
        sa.column("version"),
        sa.column("baseline_hash"),
        sa.column("package_sha256"),
        sa.column("created"),
    )
    op.execute(
        versions.insert().from_select(
            ["job_id", "version", "baseline_hash", "package_sha256", "created"],
            sa.select(jobs.c.id, jobs.c.version, jobs.c.baseline_hash, sa.literal(""), jobs.c.created).where(
                jobs.c.status == "completed"
            ),
        )
    )


def downgrade():
    op.drop_table("document_versions")
