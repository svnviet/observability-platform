from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.api_key import require_api_key, require_api_key_for_writes
from app.auth.router import router as auth_router
from app.events.router import router as events_router
from app.failures.router import router as failures_router
from app.incidents.router import router as incidents_router
from app.jobs.router import router as jobs_router
from app.monitoring.router import router as monitoring_router
from app.observability.router import incidents_router as incident_obs_router
from app.observability.router import runs_router as run_obs_router
from app.observability.router import services_router as service_obs_router
from app.observability.router import workers_router as worker_obs_router
from app.registry.router import services_router, workers_router
from app.registry.probe_scheduler import HealthProbeScheduler
from app.registry.scheduler import HeartbeatScheduler
from app.ui.router import STATIC_DIR
from app.ui.router import router as ui_router
from app.workflows.definitions_router import router as definitions_router
from app.workflows.router import router as workflows_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = HeartbeatScheduler.from_config()
    scheduler.start()
    prober = HealthProbeScheduler.from_config()
    prober.start()
    yield
    prober.stop()
    scheduler.stop()


# Interactive docs are off: the built-in /docs, /redoc and /openapi.json routes are
# unauthenticated. The schema is served below behind the API key instead.
app = FastAPI(title="Obskit Platform", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(require_api_key)])
def openapi_schema() -> dict:
    return app.openapi()


for router in (
    events_router,
    workflows_router,
    definitions_router,
    services_router,
    workers_router,
    jobs_router,
    incidents_router,
    monitoring_router,
    failures_router,
    service_obs_router,
    worker_obs_router,
    run_obs_router,
    incident_obs_router,
):
    app.include_router(router, dependencies=[Depends(require_api_key_for_writes)])
app.include_router(auth_router)

# The management UI is served at / and browses read-only data without a key. Only requests that change
# data (POST/PUT/PATCH/DELETE) and /openapi.json need the API key.
app.include_router(ui_router)
app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="ui-static")
