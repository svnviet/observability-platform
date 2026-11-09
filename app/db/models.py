import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.types import JsonType, UTCDateTime


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class ServiceRow(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("name", "environment", name="uq_services_name_env"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str | None] = mapped_column(String(100))
    environment: Mapped[str] = mapped_column(String(100), default="unknown")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, onupdate=_now)


class WorkflowDefinitionRow(Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_workflow_definitions_name_ver"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(100), default="1")
    description: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)


class WorkflowRunRow(Base):
    """Materialized current state of one workflow execution; history lives in workflow_events."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_workflow_id", "workflow_id"),
        Index("ix_workflow_runs_status", "status"),
        Index("ix_workflow_runs_started_at", "started_at"),
        Index("ix_workflow_runs_correlation_id", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    # SDK-generated identifiers (ids are minted at the edge, not by this platform).
    run_key: Mapped[str] = mapped_column(String(200), unique=True)
    workflow_id: Mapped[str] = mapped_column(String(200))
    workflow_definition_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_definitions.id"))
    status: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[str | None] = mapped_column(String(200))
    trace_id: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    input_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    output_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    definition: Mapped["WorkflowDefinitionRow | None"] = relationship()
    steps: Mapped[list["WorkflowStepRow"]] = relationship(
        back_populates="run", order_by="WorkflowStepRow.sequence_number"
    )


class WorkflowStepRow(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "step_key", name="uq_workflow_steps_run_key"),
        Index("ix_workflow_steps_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"))
    parent_step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_steps.id"))
    step_key: Mapped[str] = mapped_column(String(200))
    step_name: Mapped[str] = mapped_column(String(200))
    service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id"))
    status: Mapped[str] = mapped_column(String(20))
    latest_attempt_number: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sequence_number: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[WorkflowRunRow] = relationship(back_populates="steps")
    service: Mapped["ServiceRow | None"] = relationship()
    attempts: Mapped[list["StepAttemptRow"]] = relationship(
        back_populates="step", order_by="StepAttemptRow.attempt_number"
    )


class StepAttemptRow(Base):
    __tablename__ = "step_attempts"
    __table_args__ = (
        UniqueConstraint("workflow_step_id", "attempt_number", name="uq_step_attempts_step_num"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    workflow_step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_steps.id"))
    attempt_key: Mapped[str | None] = mapped_column(String(200))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    # Plain string until the worker registry (a later phase) provides a workers table to reference.
    worker_key: Mapped[str | None] = mapped_column(String(200))
    trace_id: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JsonType)

    step: Mapped[WorkflowStepRow] = relationship(back_populates="attempts")


class WorkflowEventRow(Base):
    """Immutable event log. Only the processing-disposition columns change (on replay)."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        Index("ix_workflow_events_run_occurred", "workflow_run_id", "occurred_at"),
        Index("ix_workflow_events_disposition", "disposition"),
        Index("ix_workflow_events_received_at", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(200), unique=True)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"))
    workflow_step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_steps.id"))
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("step_attempts.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    event_version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    source_service: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)
    disposition: Mapped[str] = mapped_column(String(20))
    disposition_reason: Mapped[str | None] = mapped_column(String(500))


class RejectedEventRow(Base):
    """Events that failed validation; kept so a bad producer can be diagnosed."""

    __tablename__ = "rejected_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    raw: Mapped[Any] = mapped_column(JsonType)
    error: Mapped[str] = mapped_column(Text)


class ServiceInstanceRow(Base):
    __tablename__ = "service_instances"
    __table_args__ = (
        UniqueConstraint("service_id", "instance_id", name="uq_service_instances_service_instance"),
        Index("ix_service_instances_status", "status"),
        Index("ix_service_instances_last_heartbeat", "last_heartbeat_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"))
    instance_id: Mapped[str] = mapped_column(String(200))
    hostname: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    last_heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JsonType, default=dict)

    service: Mapped[ServiceRow] = relationship()


class WorkerRow(Base):
    __tablename__ = "workers"
    __table_args__ = (
        UniqueConstraint("service_instance_id", "worker_name", name="uq_workers_instance_name"),
        Index("ix_workers_status", "status"),
        Index("ix_workers_last_heartbeat", "last_heartbeat_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    service_instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_instances.id"))
    worker_name: Mapped[str] = mapped_column(String(200))
    worker_type: Mapped[str] = mapped_column(String(100), default="default")
    status: Mapped[str] = mapped_column(String(20))
    # The SDK's job identifier. Jobs are reported separately, so this is not a foreign key.
    current_job_key: Mapped[str | None] = mapped_column(String(200))
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    last_heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JsonType, default=dict)

    instance: Mapped[ServiceInstanceRow] = relationship()


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("service_id", "external_job_id", name="uq_jobs_service_external"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_workflow_run", "workflow_run_id"),
        Index("ix_jobs_workflow_run_key", "workflow_run_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    external_job_id: Mapped[str] = mapped_column(String(200))
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_runs.id"))
    # The SDK's run id. Job updates and workflow events travel on separate paths, so a job can
    # arrive before its run exists; the key lets the link be made when the run appears.
    workflow_run_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JsonType, default=dict)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class IncidentRow(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_dedupe_key", "dedupe_key"),
        Index("ix_incidents_detected_at", "detected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    service_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("services.id"))
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_runs.id"))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id"))
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    # Stable key so repeated detections of one condition reuse the open incident.
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
