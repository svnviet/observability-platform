"""registry jobs incidents

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.String(length=200), nullable=False),
        sa.Column("hostname", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "instance_id", name="uq_service_instances_service_instance"),
    )
    op.create_index(
        "ix_service_instances_last_heartbeat", "service_instances", ["last_heartbeat_at"], unique=False
    )
    op.create_index("ix_service_instances_status", "service_instances", ["status"], unique=False)
    op.create_table(
        "workers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_instance_id", sa.Uuid(), nullable=False),
        sa.Column("worker_name", sa.String(length=200), nullable=False),
        sa.Column("worker_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_job_key", sa.String(length=200), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_instance_id"],
            ["service_instances.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_instance_id", "worker_name", name="uq_workers_instance_name"),
    )
    op.create_index("ix_workers_last_heartbeat", "workers", ["last_heartbeat_at"], unique=False)
    op.create_index("ix_workers_status", "workers", ["status"], unique=False)
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("worker_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_dedupe_key", "incidents", ["dedupe_key"], unique=False)
    op.create_index("ix_incidents_detected_at", "incidents", ["detected_at"], unique=False)
    op.create_index("ix_incidents_status", "incidents", ["status"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_job_id", sa.String(length=200), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_run_key", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "error_details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "external_job_id", name="uq_jobs_service_external"),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_workflow_run", "jobs", ["workflow_run_id"], unique=False)
    op.create_index("ix_jobs_workflow_run_key", "jobs", ["workflow_run_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_workflow_run_key", table_name="jobs")
    op.drop_index("ix_jobs_workflow_run", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_detected_at", table_name="incidents")
    op.drop_index("ix_incidents_dedupe_key", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_workers_status", table_name="workers")
    op.drop_index("ix_workers_last_heartbeat", table_name="workers")
    op.drop_table("workers")
    op.drop_index("ix_service_instances_status", table_name="service_instances")
    op.drop_index("ix_service_instances_last_heartbeat", table_name="service_instances")
    op.drop_table("service_instances")
