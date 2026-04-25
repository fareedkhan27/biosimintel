from __future__ import annotations

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.email_pref import (
    EmailDepartmentFilter,
    EmailOperatingModelThreshold,
    EmailPreference,
    EmailRegionFilter,
    EmailRole,
)

logger = get_logger(__name__)

DEFAULT_PREFERENCES: list[dict[str, str]] = [
    {
        "user_email": "gm@biosimintel.com",
        "user_name": "General Manager",
        "role": EmailRole.GM,
        "region_filter": EmailRegionFilter.ALL,
        "department_filter": EmailDepartmentFilter.ALL,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
    {
        "user_email": "cee_commercial@biosimintel.com",
        "user_name": "CEE/EU Commercial Head",
        "role": EmailRole.COMMERCIAL,
        "region_filter": EmailRegionFilter.CEE_EU,
        "department_filter": EmailDepartmentFilter.COMMERCIAL,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
    {
        "user_email": "latam_commercial@biosimintel.com",
        "user_name": "LATAM Commercial Head",
        "role": EmailRole.COMMERCIAL,
        "region_filter": EmailRegionFilter.LATAM,
        "department_filter": EmailDepartmentFilter.COMMERCIAL,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
    {
        "user_email": "mea_commercial@biosimintel.com",
        "user_name": "MEA Commercial Head",
        "role": EmailRole.COMMERCIAL,
        "region_filter": EmailRegionFilter.MEA,
        "department_filter": EmailDepartmentFilter.COMMERCIAL,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
    {
        "user_email": "cee_medical@biosimintel.com",
        "user_name": "CEE/EU Medical Lead",
        "role": EmailRole.MEDICAL,
        "region_filter": EmailRegionFilter.CEE_EU,
        "department_filter": EmailDepartmentFilter.MEDICAL,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
    {
        "user_email": "latam_ma@biosimintel.com",
        "user_name": "LATAM Market Access",
        "role": EmailRole.MARKET_ACCESS,
        "region_filter": EmailRegionFilter.LATAM,
        "department_filter": EmailDepartmentFilter.MARKET_ACCESS,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
    {
        "user_email": "mea_regulatory@biosimintel.com",
        "user_name": "MEA Regulatory Lead",
        "role": EmailRole.REGULATORY,
        "region_filter": EmailRegionFilter.MEA,
        "department_filter": EmailDepartmentFilter.REGULATORY,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
    {
        "user_email": "strategy@biosimintel.com",
        "user_name": "Strategy Ops Lead",
        "role": EmailRole.STRATEGY_OPS,
        "region_filter": EmailRegionFilter.ALL,
        "department_filter": EmailDepartmentFilter.ALL,
        "operating_model_threshold": EmailOperatingModelThreshold.ALL,
    },
]


async def seed_email_preferences() -> int:
    count = 0
    async with AsyncSessionLocal() as db:
        for pref in DEFAULT_PREFERENCES:
            stmt = (
                pg_insert(EmailPreference)
                .values(**pref)
                .on_conflict_do_nothing(index_elements=["user_email"])
            )
            await db.execute(stmt)
            count += 1
        await db.commit()
    logger.info("Email preferences seeded", count=count)
    return count


async def main() -> None:
    configure_logging()
    await seed_email_preferences()


if __name__ == "__main__":
    asyncio.run(main())
