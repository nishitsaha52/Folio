"""Initial repository documentation schema.

Revision ID: 001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("csrf", sa.String(100), nullable=False),
        sa.Column("oauth_state", sa.String(100), nullable=False),
        sa.Column("oauth_verifier", sa.String(150), nullable=False),
        sa.Column("oauth_started", sa.DateTime()),
        sa.Column("expires", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sessions_owner", "sessions", ["owner"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("repository", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("analysis", sa.JSON()),
        sa.Column("baseline_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
        sa.Column("credential", sa.Text(), nullable=False),
        sa.Column("worker_id", sa.String(36), nullable=False),
        sa.Column("lease_until", sa.DateTime()),
    )
    op.create_index("ix_jobs_owner", "jobs", ["owner"])
    op.create_table(
        "job_access",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("principal", sa.String(100), primary_key=True),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_hash", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reviewer", sa.String(100), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reviews_job_id", "reviews", ["job_id"])
    op.create_table(
        "test_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_hash", sa.String(64), nullable=False),
        sa.Column("test_case_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("actual", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("reviewer", sa.String(100), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_test_results_job_id", "test_results", ["job_id"])
    op.create_table(
        "audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_job_id", "audit", ["job_id"])
    op.create_table(
        "scan_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
    )


def downgrade():
    for table in ("scan_cache", "audit", "test_results", "reviews", "job_access", "jobs", "sessions"):
        op.drop_table(table)
