"""health checks

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_instance_id", sa.Uuid(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column(
            "system",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["service_instance_id"], ["service_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_health_checks_instance_time", "health_checks", ["service_instance_id", "checked_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_health_checks_instance_time", table_name="health_checks")
    op.drop_table("health_checks")
