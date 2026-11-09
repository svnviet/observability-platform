import os
import tempfile

# Must run before anything imports app.main: auth reads its key at import time.
_db_file = os.path.join(tempfile.mkdtemp(prefix="obs-tests-"), "test.db")
os.environ.setdefault("OBSKIT_PLATFORM_API_KEY", "test-key")
os.environ.setdefault("OBSKIT_PLATFORM_HEARTBEAT_SCAN_INTERVAL_S", "0")  # tests trigger scans explicitly
os.environ.setdefault(
    "OBSKIT_PLATFORM_DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_db_file}"),
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import get_database  # noqa: E402
from app.main import app  # noqa: E402

API_KEY = os.environ["OBSKIT_PLATFORM_API_KEY"]


@pytest.fixture(autouse=True)
def fresh_schema():
    engine = get_database().engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app, headers={"X-API-Key": API_KEY}) as c:
        yield c


@pytest.fixture
def anon_client() -> TestClient:
    with TestClient(app) as c:
        yield c
