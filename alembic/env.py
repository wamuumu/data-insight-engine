import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "src")
)  # Ensure src is in the path

from db.models.base import BaseModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override SQLAlchemy url from the environment variable
db_url = os.environ.get("DB_URL")
if not db_url:
    raise RuntimeError("DB_URL environment variable is not set")
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = BaseModel.metadata


def run_migrations_offline():
    """Run migrations wihtout a live DB connection (generates SQL script)"""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations with a live DB connection"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
