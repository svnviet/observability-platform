"""job events

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TERMINAL_TYPE = "'JOB_' || j.status"


def upgrade() -> None:
    op.create_table(
        "job_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("previous_status", sa.String(length=20), nullable=True),
        sa.Column("current_status", sa.String(length=20), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "detail",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_events_job_time", "job_events", ["job_id", "occurred_at"], unique=False)

    if op.get_bind().dialect.name != "postgresql":
        return
    # Jobs that existed before this table only have their current state and timestamps. Give each the
    # two transitions those timestamps prove (started, finished) so its history is not empty; the
    # previous status was not recorded, so it stays NULL, and `backfilled` marks them as reconstructed.
    op.execute(
        """
        INSERT INTO job_events (id, job_id, event_type, previous_status, current_status, service_id, worker_id,
                                occurred_at, detail)
        SELECT gen_random_uuid(), j.id, 'JOB_STARTED', NULL, 'RUNNING', j.service_id, j.worker_id, j.started_at,
               '{"backfilled": true}'::jsonb
        FROM jobs j WHERE j.started_at IS NOT NULL
        """
    )
    op.execute(
        f"""
        INSERT INTO job_events (id, job_id, event_type, previous_status, current_status, service_id, worker_id,
                                occurred_at, detail)
        SELECT gen_random_uuid(), j.id, {_TERMINAL_TYPE}, NULL, j.status, j.service_id, j.worker_id,
               j.finished_at, '{{"backfilled": true}}'::jsonb
        FROM jobs j WHERE j.finished_at IS NOT NULL AND j.status IN ('COMPLETED', 'FAILED', 'CANCELLED')
        """
    )
    op.execute(
        """
        INSERT INTO job_events (id, job_id, event_type, previous_status, current_status, service_id, worker_id,
                                occurred_at, detail)
        SELECT gen_random_uuid(), j.id, 'JOB_QUEUED', NULL, 'QUEUED', j.service_id, NULL, j.created_at,
               '{"backfilled": true}'::jsonb
        FROM jobs j WHERE j.started_at IS NULL AND j.finished_at IS NULL
        """
    )


def downgrade() -> None:
    # Lossy by nature: the job history table is dropped with its rows (jobs themselves are untouched).
    op.drop_index("ix_job_events_job_time", table_name="job_events")
    op.drop_table("job_events")
