from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.job_repository import JobRepository
from app.db.models import JobRow
from app.db.registry_repository import RegistryRepository
from app.db.workflow_repository import WorkflowRepository
from app.schemas.enums import JobStatus
from app.schemas.ops import JobRead, JobUpsertIn
from app.schemas.workflows import Page

_TERMINAL = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


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
        job = self._jobs.get_or_create(service.id, body.external_job_id)
        current = JobStatus(job.status)
        # Terminal states are final; a late RUNNING must not reopen a finished job.
        if current not in _TERMINAL:
            job.status = body.status.value
            if body.status is JobStatus.RUNNING and job.started_at is None:
                job.started_at = now
            if body.status in _TERMINAL:
                job.finished_at = now
                job.started_at = job.started_at or now
        job.metadata_ = {**job.metadata_, **body.metadata}
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
        self._session.commit()
        return self._read(job, service.name)

    def list(
        self, *, status: JobStatus | None, service: str | None, limit: int, offset: int
    ) -> Page[JobRead]:
        rows, total = self._jobs.list(status=status, service=service, limit=limit, offset=offset)
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
        )
