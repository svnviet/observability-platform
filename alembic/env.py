from sqlalchemy import create_engine

from alembic import context
from app.core.config import database_url
from app.db.models import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        # PostgreSQL DDL is transactional and Alembic runs every pending migration in ONE transaction, so a
        # failure in any of them rolls the whole upgrade back and the database stays at its previous revision.
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            if connection.dialect.name == "postgresql":
                # Fail fast (and roll back) instead of queueing behind live traffic and blocking it.
                context.execute("SET LOCAL lock_timeout = '10s'")
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
