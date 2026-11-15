from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

ROOT = Path(__file__).resolve().parents[1]


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def migration_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setenv("OBSKIT_PLATFORM_DATABASE_URL", url)
    return url


def test_every_migration_can_be_applied_and_rolled_back_one_step_at_a_time(migration_db):
    cfg = _config()
    command.upgrade(cfg, "head")
    engine = create_engine(migration_db)
    assert "trace_id" in {c["name"] for c in inspect(engine).get_columns("jobs")}

    steps = 0
    while "alembic_version" in inspect(engine).get_table_names():
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if current is None:
            break
        command.downgrade(cfg, "-1")
        steps += 1
        assert steps < 20, "downgrade did not reach the base"
    assert steps >= 5  # 0001..0005
    assert "jobs" not in inspect(engine).get_table_names()

    command.upgrade(cfg, "head")  # and forward again from empty
    assert "job_events" in inspect(create_engine(migration_db)).get_table_names()


def test_rolling_back_the_last_migration_keeps_jobs_and_their_trace_ids_readable(migration_db):
    cfg = _config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004")
    columns = {c["name"] for c in inspect(create_engine(migration_db)).get_columns("jobs")}
    assert "trace_id" not in columns and "external_job_id" in columns
