import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.enums import InstanceStatus, WorkerStatus


class ServiceRegisterIn(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    instance_id: str = Field(min_length=1, max_length=200)
    environment: str = Field(default="unknown", max_length=100)
    service_version: str | None = Field(default=None, max_length=100)
    hostname: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceRegisterOut(BaseModel):
    service_id: uuid.UUID
    instance_id: str
    status: InstanceStatus


class HeartbeatIn(BaseModel):
    instance_id: str = Field(min_length=1, max_length=200)
    stopping: bool = False  # graceful shutdown: mark the instance STOPPED instead of HEALTHY


class InstanceRead(BaseModel):
    instance_id: str
    hostname: str | None
    status: str
    last_heartbeat_at: datetime
    registered_at: datetime
    heartbeat_age_s: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceRead(BaseModel):
    id: uuid.UUID
    name: str
    version: str | None
    environment: str
    status: str  # HEALTHY, DEGRADED, UNHEALTHY, STOPPED or NO_INSTANCES
    instances_total: int
    instances_healthy: int
    last_heartbeat_at: datetime | None


class ServiceDetail(ServiceRead):
    metadata: dict[str, Any] = Field(default_factory=dict)
    instances: list[InstanceRead]


def _check_health_url(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    url = (metadata or {}).get("health_url")
    if url is not None and not (isinstance(url, str) and url.startswith(("http://", "https://"))):
        raise ValueError("metadata.health_url must start with http:// or https://")
    return metadata


class ServiceUpdateIn(BaseModel):
    """Only the fields given change. `metadata` is merged; a key set to null is removed.

    Name and environment are the service's identity and cannot be edited: register under the new name instead.
    """

    version: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] | None = None


class InstanceUpdateIn(BaseModel):
    hostname: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] | None = None

    _health_url = field_validator("metadata")(_check_health_url)


class WorkerUpdateIn(BaseModel):
    worker_type: str | None = Field(default=None, min_length=1, max_length=100)
    capacity: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] | None = None


class DeleteResult(BaseModel):
    """What a delete removed. History (jobs, incidents, workflow runs) is kept unless stated otherwise."""

    deleted: str  # service | instance | worker | workflow_run
    instances: int = 0
    workers: int = 0
    jobs: int = 0
    events: int = 0


class WorkerRegisterIn(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    instance_id: str = Field(min_length=1, max_length=200)
    worker_name: str = Field(min_length=1, max_length=200)
    environment: str = Field(default="unknown", max_length=100)
    service_version: str | None = Field(default=None, max_length=100)
    worker_type: str = Field(default="default", max_length=100)
    capacity: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerHeartbeatIn(BaseModel):
    status: WorkerStatus | None = None
    current_job_id: str | None = Field(default=None, max_length=200)


class WorkerStatusIn(BaseModel):
    status: WorkerStatus
    current_job_id: str | None = Field(default=None, max_length=200)


class WorkerRead(BaseModel):
    id: uuid.UUID
    worker_name: str
    worker_type: str
    service_name: str
    environment: str
    instance_id: str
    status: str
    current_job_id: str | None
    capacity: int
    last_heartbeat_at: datetime
    registered_at: datetime
    heartbeat_age_s: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthUrlIn(BaseModel):
    health_url: str | None = Field(default=None, max_length=500)  # null stops active probing

    @field_validator("health_url")
    @classmethod
    def _http_only(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("health_url must start with http:// or https://")
        return value


class HealthUrlOut(BaseModel):
    service_id: uuid.UUID
    instance_id: str
    health_url: str | None
