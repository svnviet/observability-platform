import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.job_repository import JobRepository
from app.db.models import JobRow
from app.db.registry_repository import RegistryRepository
from app.db.workflow_repository import WorkflowRepository
from app.schemas.enums import JobStatus
from app.jobs.links import link, logs_link, metrics_link
from app.schemas.ops import JobEventRead, JobObservability, JobRead, JobTimeline, JobUpsertIn
from app.schemas.workflows import Page
from app.workflows.service import trace_url

_TERMINAL = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
_EVENT_TYPE = {
    JobStatus.QUEUED: "JOB_QUEUED",
    JobStatus.RUNNING: "JOB_STARTED",
    JobStatus.COMPLETED: "JOB_COMPLETED",
    JobStatus.FAILED: "JOB_FAILED",
    JobStatus.CANCELLED: "JOB_CANCELLED",
}


class JobService:
    def __init__(
        self,
        session: Session,
        jobs: JobRepository,
        workflows: WorkflowRepository,
        registry: RegistryRepository,
    ) -> None:
        self._session = session
        self._jobs = jobs
        self._workflows = workflows
        self._registry = registry

    def upsert(self, body: JobUpsertIn) -> JobRead:
        now = datetime.now(UTC)
        service = self._workflows.upsert_service(body.service_name, body.environment, None)
        job, created = self._jobs.get_or_create(service.id, body.external_job_id)
        current = JobStatus(job.status)
        previous_status = None if created else current.value
        if created:
            job.created_at = now  # one clock reading for creation, start and the first event
        # Terminal states are final; a late RUNNING must not reopen a finished job.
        if current not in _TERMINAL:
            job.status = body.status.value
            if body.status is JobStatus.RUNNING and job.started_at is None:
                job.started_at = now
            if body.status in _TERMINAL:
                job.finished_at = now
                job.started_at = job.started_at or now
        job.metadata_ = {**job.metadata_, **body.metadata}
        if body.trace_id:
            job.trace_id = body.trace_id
        if body.error is not None:
            job.error_details = body.error
        if body.workflow_run_key:
            job.workflow_run_key = body.workflow_run_key
            run = self._workflows.find_run_by_key(body.workflow_run_key)
            if run is not None:
                job.workflow_run_id = run.id
        if body.instance_id and body.worker_name:
            instance = self._registry.find_instance(service.id, body.instance_id)
            worker = self._registry.find_worker(instance, body.worker_name) if instance else None
            if worker is not None:
                job.worker_id = worker.id
        if job.status != previous_status:  # a repeated or refused update changes nothing, so it records nothing
            detail = {"error": body.error} if body.error is not None and job.status == JobStatus.FAILED.value else {}
            self._jobs.add_event(
                job, _EVENT_TYPE[JobStatus(job.status)], previous_status, job.status, now, detail
            )
        self._session.commit()
        return self._read(job, service.name)

    def get(self, job_id: uuid.UUID) -> JobRead | None:
        found = self._jobs.get(job_id)
        return None if found is None else self._read(*found)

    def events(self, job_id: uuid.UUID) -> list[JobEventRead] | None:
        if self._jobs.get(job_id) is None:
            return None
        return [JobEventRead.model_validate(e, from_attributes=True) for e in self._jobs.events(job_id)]

    def timeline(self, job_id: uuid.UUID) -> JobTimeline | None:
        found = self._jobs.get(job_id)
        if found is None:
            return None
        job, name = found
        now = datetime.now(UTC)
        end = job.finished_at or now
        started = job.started_at
        return JobTimeline(
            job=self._read(job, name),
            events=[JobEventRead.model_validate(e, from_attributes=True) for e in self._jobs.events(job_id)],
            # clamped: rows written before creation and start shared one clock could differ by a few ms
            queued_s=max(0.0, (started - job.created_at).total_seconds()) if started else None,
            running_s=max(0.0, (end - started).total_seconds()) if started else None,
            total_s=max(0.0, (end - job.created_at).total_seconds()),
        )

    def observability(self, job_id: uuid.UUID) -> JobObservability | None:
        found = self._jobs.get(job_id)
        if found is None:
            return None
        job, name = found
        run = self._jobs.run(job.workflow_run_id)
        worker = self._jobs.worker(job.worker_id)
        trace_id = job.trace_id or (run.trace_id if run else None)
        values = {
            "trace_id": trace_id,
            "job_id": job.external_job_id,
            "service": name,
            "worker": worker.worker_name if worker else None,
            "workflow_id": run.workflow_id if run else None,
        }
        return JobObservability(
            job_id=job.external_job_id,
            id=job.id,
            service_id=job.service_id,
            service_name=name,
            worker_id=job.worker_id,
            worker_name=values["worker"],
            workflow_run_id=job.workflow_run_id,
            workflow_id=values["workflow_id"],
            trace_id=trace_id,
            logs=logs_link(values),
            trace=link(trace_url(trace_id)),
            metrics=metrics_link(values),
        )

    def list(
        self,
        *,
        status: JobStatus | None,
        service: str | None,
        external_job_id: str | None,
        limit: int,
        offset: int,
    ) -> Page[JobRead]:
        rows, total = self._jobs.list(
            status=status, service=service, external_job_id=external_job_id, limit=limit, offset=offset
        )
        return Page(items=[self._read(j, name) for j, name in rows], total=total, limit=limit, offset=offset)

    @staticmethod
    def _read(job: JobRow, service_name: str) -> JobRead:
        return JobRead(
            id=job.id,
            external_job_id=job.external_job_id,
            service_name=service_name,
            worker_id=job.worker_id,
            workflow_run_id=job.workflow_run_id,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            metadata=job.metadata_,
            error_details=job.error_details,
            trace_id=job.trace_id,
        )
