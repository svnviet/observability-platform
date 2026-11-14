import uuid
from datetime import UTC, datetime, timedelta

from app.db.event_repository import EventRepository
from app.db.failure_repository import FailureRepository
from app.db.job_repository import JobRepository
from app.db.models import StepAttemptRow, WorkflowRunRow, WorkflowStepRow
from app.db.workflow_repository import WorkflowRepository
from app.events.state_machine import STEP_TERMINAL
from app.failures.classifier import ErrorClassifier
from app.schemas.enums import JobStatus, StepStatus, WorkflowStatus
from app.schemas.failure import FailureAnalysis, Occurrence, Precedent, RootCause
from app.schemas.ops import IncidentRead

_FAILED_RUN = frozenset({WorkflowStatus.FAILED.value, WorkflowStatus.TIMED_OUT.value})
_PRECEDENTS = 10


class FailureAnalysisService:
    """Answers 'why did this fail, where, and is it new?' from what the platform already stores."""

    def __init__(
        self,
        jobs: JobRepository,
        workflows: WorkflowRepository,
        events: EventRepository,
        failures: FailureRepository,
    ) -> None:
        self._jobs = jobs
        self._workflows = workflows
        self._events = events
        self._failures = failures

    # --- job --------------------------------------------------------------------------------

    def job(self, job_id: uuid.UUID) -> FailureAnalysis | None:
        found = self._jobs.get(job_id)
        if found is None:
            return None
        job, service_name = found
        run = self._jobs.run(job.workflow_run_id)
        trace_id = job.trace_id or (run.trace_id if run else None)
        if job.status != JobStatus.FAILED.value:
            return self._not_failed("job", job.id, job.external_job_id, job.status, trace_id)

        error = job.error_details or {}
        worker = self._jobs.worker(job.worker_id)
        root = self._root_cause(
            "job", error, service_name, worker.worker_name if worker else None, None, None, job.finished_at
        )
        ref = job.finished_at or datetime.now(UTC)
        same = [
            j.finished_at
            for j in self._failures.failed_jobs(job.service_id, ref - timedelta(days=7), ref)
            if ErrorClassifier.signature(j.error_details) == ErrorClassifier.signature(error)
        ]
        precedents = [
            Precedent(at=e.occurred_at, what=f"{e.event_type}", detail=_status_change(e.previous_status, e.current_status))
            for e in self._jobs.events(job.id)
            if job.finished_at is None or e.occurred_at < job.finished_at
        ]
        if run is not None:
            precedents += self._run_precedents(run, job.finished_at)
        impact = []
        if run is not None:
            impact.append(f"Part of workflow run {run.workflow_id} (status {run.status})")
        incidents = self._failures.incidents_around(
            at=job.finished_at, worker_id=job.worker_id, service_id=job.service_id
        )
        return FailureAnalysis(
            kind="job",
            id=job.id,
            label=job.external_job_id,
            status=job.status,
            failed=True,
            summary=self._summary(f"Job {job.external_job_id}", root),
            root_cause=root,
            impact=impact,
            precedents=sorted(precedents, key=lambda p: p.at)[-_PRECEDENTS:],
            occurrences=self._occurrence(same, ref),
            incidents=[IncidentRead.model_validate(i, from_attributes=True) for i in incidents],
            trace_id=trace_id,
        )

    # --- workflow run -----------------------------------------------------------------------

    def run(self, run_id: uuid.UUID) -> FailureAnalysis | None:
        run = self._workflows.get_run_with_steps(run_id)
        if run is None:
            return None
        label = run.definition.name if run.definition else run.workflow_id
        if run.status not in _FAILED_RUN:
            return self._not_failed("workflow_run", run.id, label, run.status, run.trace_id)

        culprit = self._first_failed_step(run)
        if culprit is not None:
            step, attempt = culprit
            error = attempt.error_details or run.error_details or {}
            root = self._root_cause(
                "step_attempt",
                error,
                step.service.name if step.service else None,
                attempt.worker_key,
                step.step_name,
                attempt.attempt_number,
                attempt.finished_at or run.finished_at,
            )
            ref = root.occurred_at or datetime.now(UTC)
            same = [
                a.finished_at
                for a, s in self._failures.failed_attempts(ref - timedelta(days=7), ref)
                if s.step_name == step.step_name
                and ErrorClassifier.signature(a.error_details) == ErrorClassifier.signature(error)
            ]
            impact = self._impact(run, step, attempt)
        else:
            error = run.error_details or {}
            root = self._root_cause("workflow", error, None, None, None, None, run.finished_at)
            same = []
            impact = ["The run failed without a failed step: the error was reported on the workflow itself"]
        failed_jobs = [j for j in self._failures.jobs_of_run(run.id) if j.status == JobStatus.FAILED.value]
        if failed_jobs:
            impact.append(f"{len(failed_jobs)} job(s) of this run failed")
        incidents = self._failures.incidents_around(at=root.occurred_at, run_id=run.id)
        return FailureAnalysis(
            kind="workflow_run",
            id=run.id,
            label=label,
            status=run.status,
            failed=True,
            summary=self._summary(f"Workflow {label}", root),
            root_cause=root,
            impact=impact,
            precedents=self._run_precedents(run, root.occurred_at),
            occurrences=self._occurrence(same, root.occurred_at or datetime.now(UTC)) if same else None,
            incidents=[IncidentRead.model_validate(i, from_attributes=True) for i in incidents],
            trace_id=run.trace_id,
        )

    # --- helpers ----------------------------------------------------------------------------

    @staticmethod
    def _first_failed_step(run: WorkflowRunRow) -> tuple[WorkflowStepRow, StepAttemptRow] | None:
        """The earliest step that ended FAILED, with its last failed attempt.

        Steps that failed once and then succeeded on retry are not the cause, so only steps whose
        final status is FAILED count.
        """
        candidates = []
        for step in run.steps:
            if step.status != StepStatus.FAILED.value:
                continue
            failed = [a for a in step.attempts if a.status == "FAILED"]
            if failed:
                attempt = failed[-1]
                candidates.append((attempt.finished_at or step.finished_at or run.finished_at, step, attempt))
        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0] is None, c[0] or datetime.max.replace(tzinfo=UTC)))
        _, step, attempt = candidates[0]
        return step, attempt

    @staticmethod
    def _impact(run: WorkflowRunRow, step: WorkflowStepRow, attempt: StepAttemptRow) -> list[str]:
        impact = []
        if len(step.attempts) > 1:
            impact.append(f"Step {step.step_name} was tried {len(step.attempts)} times before giving up")
        terminal = {x.value for x in STEP_TERMINAL}
        waiting = [
            s.step_name
            for s in run.steps
            if s.id != step.id
            and (
                s.status == StepStatus.SKIPPED.value
                or (s.sequence_number > step.sequence_number and s.status not in terminal)
            )
        ]
        if waiting:
            impact.append(f"Not completed because of it: {', '.join(waiting)}")
        return impact

    def _run_precedents(self, run: WorkflowRunRow, before: datetime | None) -> list[Precedent]:
        events = [
            e for e in self._events.all_for_run_ordered(run.id) if before is None or e.occurred_at <= before
        ]
        return [
            Precedent(at=e.occurred_at, what=e.event_type, detail=f"{e.source_service} ({e.disposition})")
            for e in events[-_PRECEDENTS:]
        ]

    @staticmethod
    def _root_cause(
        source: str,
        error: dict,
        service_name: str | None,
        worker: str | None,
        step_name: str | None,
        attempt_number: int | None,
        occurred_at: datetime | None,
    ) -> RootCause:
        stack = ErrorClassifier.stack_trace(error)
        category, reason = ErrorClassifier.classify(error)
        return RootCause(
            source=source,
            service_name=service_name,
            worker=worker,
            step_name=step_name,
            attempt_number=attempt_number,
            error_type=error.get("type"),
            message=error.get("message"),
            stack_trace=stack,
            location=ErrorClassifier.location(stack),
            category=category,
            category_reason=reason,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _occurrence(times: list[datetime | None], ref: datetime) -> Occurrence:
        """Counts are taken up to `ref` (the failure itself), so an old failure is judged by its own week."""
        seen = sorted(t for t in times if t is not None)
        return Occurrence(
            count_24h=sum(1 for t in seen if t >= ref - timedelta(hours=24)),
            count_7d=len(seen),
            first_seen=seen[0] if seen else None,
            last_seen=seen[-1] if seen else None,
            is_new=len(seen) <= 1,
        )

    @staticmethod
    def _summary(subject: str, root: RootCause) -> str:
        where = " in ".join(x for x in (f"step {root.step_name}" if root.step_name else None, root.service_name) if x)
        what = root.error_type or (root.message or "an unrecorded error")[:80]
        cause = f" ({root.category.lower()})" if root.category != "UNKNOWN" else ""
        return f"{subject} failed{f' at {where}' if where else ''}: {what}{cause}"

    @staticmethod
    def _not_failed(kind: str, id_: uuid.UUID, label: str, status: str, trace_id: str | None) -> FailureAnalysis:
        return FailureAnalysis(
            kind=kind, id=id_, label=label, status=status, failed=False,
            summary=f"{label} is {status}: nothing has failed.",
            root_cause=None, impact=[], precedents=[], occurrences=None, incidents=[], trace_id=trace_id,
        )  # fmt: skip


def _status_change(previous: str | None, current: str) -> str:
    return f"{previous} -> {current}" if previous else current
