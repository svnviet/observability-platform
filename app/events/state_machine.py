from app.schemas.enums import Disposition, EventType, StepStatus, WorkflowStatus

WORKFLOW_TERMINAL = frozenset(
    {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.TIMED_OUT,
    }
)
STEP_TERMINAL = frozenset({StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED, StepStatus.CANCELLED})

_WORKFLOW_RANK = {
    WorkflowStatus.CREATED: 0,
    WorkflowStatus.QUEUED: 1,
    WorkflowStatus.RUNNING: 2,
    **{s: 3 for s in WORKFLOW_TERMINAL},
}
_STEP_RANK = {
    StepStatus.PENDING: 0,
    StepStatus.QUEUED: 1,
    StepStatus.RUNNING: 2,
    StepStatus.RETRYING: 3,
    **{s: 4 for s in STEP_TERMINAL},
}

WORKFLOW_TARGET = {
    EventType.WORKFLOW_CREATED: WorkflowStatus.CREATED,
    EventType.WORKFLOW_QUEUED: WorkflowStatus.QUEUED,
    EventType.WORKFLOW_STARTED: WorkflowStatus.RUNNING,
    EventType.WORKFLOW_COMPLETED: WorkflowStatus.COMPLETED,
    EventType.WORKFLOW_FAILED: WorkflowStatus.FAILED,
    EventType.WORKFLOW_CANCELLED: WorkflowStatus.CANCELLED,
    EventType.WORKFLOW_TIMED_OUT: WorkflowStatus.TIMED_OUT,
}
STEP_TARGET = {
    EventType.STEP_QUEUED: StepStatus.QUEUED,
    EventType.STEP_STARTED: StepStatus.RUNNING,
    EventType.STEP_COMPLETED: StepStatus.COMPLETED,
    EventType.STEP_FAILED: StepStatus.FAILED,
    EventType.STEP_SKIPPED: StepStatus.SKIPPED,
    EventType.STEP_CANCELLED: StepStatus.CANCELLED,
}


class TransitionPolicy:
    """Decides whether an event advances state.

    Progress is monotonic, so the outcome does not depend on arrival order:
    a late STARTED after COMPLETED is stale, never a regression. A step's order key is
    (attempt_number, status rank), so a higher attempt supersedes a failed lower one.
    """

    @staticmethod
    def workflow(current: WorkflowStatus, target: WorkflowStatus) -> tuple[Disposition, str | None]:
        if current in WORKFLOW_TERMINAL:
            if target == current:
                return Disposition.STALE, "already in this terminal state"
            if target in WORKFLOW_TERMINAL:
                return Disposition.QUARANTINED, f"conflicting terminal state {target} after {current}"
            return Disposition.STALE, f"late event after terminal state {current}"
        if _WORKFLOW_RANK[target] > _WORKFLOW_RANK[current]:
            return Disposition.APPLIED, None
        return Disposition.STALE, f"{target} does not advance {current}"

    @staticmethod
    def step(
        current: StepStatus, current_attempt: int, attempt: int, target: StepStatus
    ) -> tuple[Disposition, str | None]:
        if attempt == current_attempt and current in STEP_TERMINAL and target in STEP_TERMINAL:
            if target == current:
                return Disposition.STALE, "already in this terminal state"
            return Disposition.QUARANTINED, f"conflicting terminal state {target} after {current}"
        if (attempt, _STEP_RANK[target]) > (current_attempt, _STEP_RANK[current]):
            return Disposition.APPLIED, None
        return Disposition.STALE, f"{target} (attempt {attempt}) does not advance {current}"
