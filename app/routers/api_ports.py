from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.port import Port

router = APIRouter(prefix="/api/ports", tags=["api-ports"])


@router.get("/search")
async def search_ports(
    q: str = Query("", min_length=1),
    limit: int = Query(15, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search ports by LOCODE or name for autocomplete."""
    search = f"%{q.upper()}%"
    result = await db.execute(
        select(Port)
        .where(
            or_(
                Port.locode.ilike(search),
                Port.name.ilike(f"%{q}%"),
            )
        )
        .order_by(Port.is_shortcut.desc(), Port.locode)
        .limit(limit)
    )
    ports = result.scalars().all()
    return JSONResponse([
        {
            "locode": p.locode,
            "name": p.name,
            "country_code": p.country_code,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "is_shortcut": p.is_shortcut,
        }
        for p in ports
    ])


@router.get("/shortcuts")
async def shortcut_ports(db: AsyncSession = Depends(get_db)):
    """Get shortcut ports (Fécamp, São Sebastião)."""
    result = await db.execute(
        select(Port).where(Port.is_shortcut == True).order_by(Port.locode)
    )
    ports = result.scalars().all()
    return JSONResponse([
        {
            "locode": p.locode,
            "name": p.name,
            "country_code": p.country_code,
        }
        for p in ports
    ])
