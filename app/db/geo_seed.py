from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.models.geo import Country, OperatingModel, Region, RegionCode

logger = get_logger(__name__)

REGIONS = [
    {"name": "Central & Eastern Europe / EU", "code": RegionCode.CEE_EU},
    {"name": "Latin America", "code": RegionCode.LATAM},
    {"name": "Middle East & Africa", "code": RegionCode.MEA},
]

# fmt: off
COUNTRIES = [
    # CEE/EU LPM
    {"name": "Israel", "code": "IL", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "ILS"},
    {"name": "Kazakhstan", "code": "KZ", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "KZT"},
    {"name": "Malta", "code": "MT", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "EUR"},
    {"name": "Russia", "code": "RU", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "Roszdravnadzor", "local_currency_code": "RUB"},
    # CEE/EU OPM
    {"name": "Albania", "code": "AL", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "ALL"},
    {"name": "Bosnia", "code": "BA", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "BAM"},
    {"name": "Bulgaria", "code": "BG", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "BDA", "local_currency_code": "BGN"},
    {"name": "Croatia", "code": "HR", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "HALMED", "local_currency_code": "EUR"},
    {"name": "Estonia", "code": "EE", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "SAM", "local_currency_code": "EUR"},
    {"name": "Kosovo", "code": "XK", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "EUR"},
    {"name": "Latvia", "code": "LV", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "EUR"},
    {"name": "Lithuania", "code": "LT", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "EUR"},
    {"name": "Macedonia", "code": "MK", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "MKD"},
    {"name": "Montenegro", "code": "ME", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "EUR"},
    {"name": "Serbia", "code": "RS", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "ALIMS", "local_currency_code": "RSD"},
    {"name": "Slovakia", "code": "SK", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "SUKL", "local_currency_code": "EUR"},
    {"name": "Slovenia", "code": "SI", "region_code": RegionCode.CEE_EU, "operating_model": OperatingModel.OPM, "local_regulatory_agency_name": "JAZMP", "local_currency_code": "EUR"},
    # LATAM LPM
    {"name": "Bolivia", "code": "BO", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "BOB"},
    {"name": "Brazil", "code": "BR", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "ANVISA", "local_currency_code": "BRL"},
    {"name": "Costa Rica", "code": "CR", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "CRC"},
    {"name": "Dominican Republic", "code": "DO", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "DOP"},
    {"name": "Ecuador", "code": "EC", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "USD"},
    {"name": "El Salvador", "code": "SV", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "USD"},
    {"name": "Guatemala", "code": "GT", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "GTQ"},
    {"name": "Honduras", "code": "HN", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "HNL"},
    {"name": "Nicaragua", "code": "NI", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "NIO"},
    {"name": "Panama", "code": "PA", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "USD"},
    {"name": "Paraguay", "code": "PY", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "PYG"},
    {"name": "Uruguay", "code": "UY", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "UYU"},
    # LATAM Passive
    {"name": "Venezuela", "code": "VE", "region_code": RegionCode.LATAM, "operating_model": OperatingModel.Passive, "local_regulatory_agency_name": "TODO", "local_currency_code": "VES"},
    # MEA LPM
    {"name": "Algeria", "code": "DZ", "region_code": RegionCode.MEA, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "ANPP", "local_currency_code": "DZD"},
    {"name": "Egypt", "code": "EG", "region_code": RegionCode.MEA, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "EDA", "local_currency_code": "EGP"},
    {"name": "Iraq", "code": "IQ", "region_code": RegionCode.MEA, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "IQD"},
    {"name": "Lebanon", "code": "LB", "region_code": RegionCode.MEA, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "LBP"},
    {"name": "Libya", "code": "LY", "region_code": RegionCode.MEA, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "LYD"},
    {"name": "Morocco", "code": "MA", "region_code": RegionCode.MEA, "operating_model": OperatingModel.LPM, "local_regulatory_agency_name": "TODO", "local_currency_code": "MAD"},
    # MEA Passive
    {"name": "South Africa", "code": "ZA", "region_code": RegionCode.MEA, "operating_model": OperatingModel.Passive, "local_regulatory_agency_name": "SAHPRA", "local_currency_code": "ZAR"},
]
# fmt: on


async def seed_regions(db: AsyncSession) -> dict[RegionCode, str]:
    """Upsert regions and return mapping code -> id."""
    region_map: dict[RegionCode, str] = {}

    for region_data in REGIONS:
        stmt = (
            pg_insert(Region)
            .values(**region_data)
            .on_conflict_do_nothing(index_elements=["code"])
        )
        await db.execute(stmt)

    await db.commit()

    result = await db.execute(select(Region))
    for region in result.scalars().all():
        code: RegionCode = region.code  # type: ignore[assignment]
        region_map[code] = str(region.id)

    logger.info("Regions seeded", count=len(region_map))
    return region_map


async def seed_countries(db: AsyncSession, region_map: dict[RegionCode, str]) -> int:
    """Upsert countries using resolved region IDs."""
    for country_data in COUNTRIES:
        data = dict(country_data)
        region_code: RegionCode = data.pop("region_code")  # type: ignore[assignment]
        region_id = region_map[region_code]

        stmt = (
            pg_insert(Country)
            .values(region_id=region_id, **data)
            .on_conflict_do_nothing(index_elements=["code"])
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Countries seeded", total=len(COUNTRIES))
    return len(COUNTRIES)


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        region_map = await seed_regions(db)
        await seed_countries(db, region_map)


if __name__ == "__main__":
    asyncio.run(main())
