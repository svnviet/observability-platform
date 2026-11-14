import uuid

from pydantic import BaseModel

from app.schemas.ops import ObservabilityLink


class EntityRef(BaseModel):
    type: str  # service | worker | workflow_run | incident
    id: uuid.UUID


class EntityObservability(BaseModel):
    """Where to look at one entity's telemetry. Links only; no log, trace or metric data passes through OBS."""

    entity: EntityRef
    correlation: dict[str, str | None]  # the ids the telemetry backends are keyed by
    links: dict[str, ObservabilityLink]  # logs, trace, metrics, dashboard
    capabilities: dict[str, bool]  # which links are usable, so a UI shows only what works
