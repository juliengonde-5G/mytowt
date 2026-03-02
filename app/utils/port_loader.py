"""
Port loader utility — imports seaports from UN/LOCODE open dataset.

Sources:
 - GitHub datasets/un-locode (CSV)
 - data.gouv.fr Seaports Locations Data (Upply)

Filters: only locations with Function[0] == '1' (seaport).
"""

import csv
import io
import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.port import Port

logger = logging.getLogger(__name__)

# UN/LOCODE full dataset from GitHub (always up-to-date)
UNLOCODE_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/un-locode/main/data/code-list.csv"
)

# data.gouv.fr Upply seaports (user-provided URL — may have richer data)
DATAGOUV_CSV_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/9fab52ee-09e3-4ab8-8d75-ef43a33771bc"
)


def parse_unlocode_coordinates(coord_str: str) -> tuple[Optional[float], Optional[float]]:
    """Parse UN/LOCODE coordinate string like '4230N 00131E' → (42.5, 1.5167)."""
    if not coord_str or not coord_str.strip():
        return None, None
    try:
        parts = coord_str.strip().split()
        if len(parts) != 2:
            return None, None

        lat_str, lon_str = parts

        # Latitude: DDMMN/S
        lat_dir = lat_str[-1]
        lat_deg = int(lat_str[:2])
        lat_min = int(lat_str[2:-1])
        lat = lat_deg + lat_min / 60.0
        if lat_dir == "S":
            lat = -lat

        # Longitude: DDDMME/W
        lon_dir = lon_str[-1]
        lon_deg = int(lon_str[:3])
        lon_min = int(lon_str[3:-1])
        lon = lon_deg + lon_min / 60.0
        if lon_dir == "W":
            lon = -lon

        return lat, lon
    except (ValueError, IndexError):
        return None, None


async def load_ports_from_unlocode(db: AsyncSession) -> dict:
    """
    Download UN/LOCODE CSV and insert seaports into the database.
    Returns stats: {inserted, updated, skipped, errors}.
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0, "total_rows": 0}

    # Download CSV
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(UNLOCODE_CSV_URL)
        resp.raise_for_status()

    content = resp.text
    reader = csv.DictReader(io.StringIO(content))

    # Load existing ports for fast lookup
    existing_result = await db.execute(select(Port))
    existing_ports = {p.locode: p for p in existing_result.scalars().all()}

    for row in reader:
        stats["total_rows"] += 1
        country = (row.get("Country") or "").strip()
        location = (row.get("Location") or "").strip()
        name = (row.get("Name") or "").strip()
        function_code = (row.get("Function") or "").strip()
        coordinates = (row.get("Coordinates") or "").strip()

        if not country or not location or not name:
            stats["skipped"] += 1
            continue

        # Filter: only seaports (Function position 0 == '1')
        if len(function_code) < 1 or function_code[0] != "1":
            stats["skipped"] += 1
            continue

        locode = f"{country}{location}"  # e.g. FRFEC

        lat, lon = parse_unlocode_coordinates(coordinates)

        if locode in existing_ports:
            # Update name/coordinates if missing
            port = existing_ports[locode]
            changed = False
            if not port.latitude and lat:
                port.latitude = lat
                changed = True
            if not port.longitude and lon:
                port.longitude = lon
                changed = True
            if changed:
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        else:
            port = Port(
                locode=locode,
                name=name,
                country_code=country,
                latitude=lat,
                longitude=lon,
                is_shortcut=False,
            )
            db.add(port)
            existing_ports[locode] = port
            stats["inserted"] += 1

    await db.flush()
    logger.info(
        "Port import done: %d inserted, %d updated, %d skipped, %d errors (from %d rows)",
        stats["inserted"], stats["updated"], stats["skipped"], stats["errors"], stats["total_rows"],
    )
    return stats
