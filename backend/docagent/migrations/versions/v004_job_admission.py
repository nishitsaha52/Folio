"""Serialize queue admission so concurrent requests cannot bypass job limits."""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table("job_admission", sa.Column("id", sa.Integer(), primary_key=True))
    op.bulk_insert(table, [{"id": 1}])


def downgrade():
    op.drop_table("job_admission")
