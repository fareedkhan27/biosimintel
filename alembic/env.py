from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import make_url, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import settings
from app.db.session import Base
from app.models.combo import (
    CompetitorMoleculeAssignment,  # noqa: F401
    MoleculePair,  # noqa: F401
)
from app.models.competitor import Competitor  # noqa: F401
from app.models.data_provenance import DataProvenance  # noqa: F401
from app.models.email_pref import EmailPreference  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.geo import (
    CompetitorCapability,  # noqa: F401
    Country,  # noqa: F401
    Region,  # noqa: F401
)
from app.models.intelligence_baseline import IntelligenceBaseline  # noqa: F401
from app.models.llm_insight_cache import LlmInsightCache  # noqa: F401

# Import all models so they are registered with Base metadata
from app.models.molecule import Molecule  # noqa: F401
from app.models.noise import NoiseSignal  # noqa: F401
from app.models.patent_cliff import PatentCliff  # noqa: F401
from app.models.review import Review  # noqa: F401
from app.models.scoring_rule import ScoringRule  # noqa: F401
from app.models.sec_filing import SecFiling  # noqa: F401
from app.models.signal import GeoSignal  # noqa: F401
from app.models.source_document import SourceDocument  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return str(settings.DATABASE_URL)


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section)
    if configuration is None:
        raise RuntimeError("Alembic configuration section not found")

    url = make_url(get_url())
    # asyncpg does not accept sslmode/channel_binding as kwargs
    filtered_query = {k: v for k, v in url.query.items() if k not in ("sslmode", "channel_binding")}
    url = url.set(query=filtered_query)

    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"ssl": True},  # Neon requires SSL
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
