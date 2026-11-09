"""initial schema

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rejected_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=True),
        sa.Column("environment", sa.String(length=100), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "environment", name="uq_services_name_env"),
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "definition",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_workflow_definitions_name_ver"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_key", sa.String(length=200), nullable=False),
        sa.Column("workflow_id", sa.String(length=200), nullable=False),
        sa.Column("workflow_definition_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("correlation_id", sa.String(length=200), nullable=True),
        sa.Column("trace_id", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "input_metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "output_metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "error_details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_definition_id"],
            ["workflow_definitions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key"),
    )
    op.create_index("ix_workflow_runs_correlation_id", "workflow_runs", ["correlation_id"], unique=False)
    op.create_index("ix_workflow_runs_started_at", "workflow_runs", ["started_at"], unique=False)
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"], unique=False)
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"], unique=False)
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("parent_step_id", sa.Uuid(), nullable=True),
        sa.Column("step_key", sa.String(length=200), nullable=False),
        sa.Column("step_name", sa.String(length=200), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("latest_attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_step_id"],
            ["workflow_steps.id"],
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "step_key", name="uq_workflow_steps_run_key"),
    )
    op.create_index("ix_workflow_steps_status", "workflow_steps", ["status"], unique=False)
    op.create_table(
        "step_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_step_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_key", sa.String(length=200), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("worker_key", sa.String(length=200), nullable=True),
        sa.Column("trace_id", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "error_details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_step_id"],
            ["workflow_steps.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_step_id", "attempt_number", name="uq_step_attempts_step_num"),
    )
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_step_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_service", sa.String(length=200), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("disposition_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["step_attempts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_step_id"],
            ["workflow_steps.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_workflow_events_disposition", "workflow_events", ["disposition"], unique=False)
    op.create_index("ix_workflow_events_received_at", "workflow_events", ["received_at"], unique=False)
    op.create_index(
        "ix_workflow_events_run_occurred", "workflow_events", ["workflow_run_id", "occurred_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_events_run_occurred", table_name="workflow_events")
    op.drop_index("ix_workflow_events_received_at", table_name="workflow_events")
    op.drop_index("ix_workflow_events_disposition", table_name="workflow_events")
    op.drop_table("workflow_events")
    op.drop_table("step_attempts")
    op.drop_index("ix_workflow_steps_status", table_name="workflow_steps")
    op.drop_table("workflow_steps")
    op.drop_index("ix_workflow_runs_workflow_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_started_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_correlation_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflow_definitions")
    op.drop_table("services")
    op.drop_table("rejected_events")
