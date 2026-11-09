import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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
    instances: list[InstanceRead]


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
