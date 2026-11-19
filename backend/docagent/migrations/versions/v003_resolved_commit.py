"""Persist the source commit before processing so worker recovery is reproducible."""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("resolved_commit", sa.String(40), nullable=False, server_default=""))


def downgrade():
    op.drop_column("jobs", "resolved_commit")
