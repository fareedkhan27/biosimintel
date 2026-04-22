from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

Base = declarative_base()

url = make_url(str(settings.DATABASE_URL))
filtered_query = {k: v for k, v in url.query.items() if k not in ("sslmode", "channel_binding")}
url = url.set(query=filtered_query)

engine = create_async_engine(
    url,
    echo=settings.DEBUG,
    future=True,
    connect_args={"ssl": True},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to yield an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
