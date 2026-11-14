"""jobs.trace_id column

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("trace_id", sa.String(length=200), nullable=True))
    op.create_index("ix_jobs_trace_id", "jobs", ["trace_id"], unique=False)
    if op.get_bind().dialect.name != "postgresql":
        return
    # Until now the trace id lived inside jobs.metadata; move it so jobs can be found and joined by it.
    op.execute(
        """
        UPDATE jobs SET trace_id = left(metadata ->> 'trace_id', 200)
        WHERE trace_id IS NULL AND metadata ->> 'trace_id' IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_trace_id", table_name="jobs")
    op.drop_column("jobs", "trace_id")
