"""Purge all passenger bookings except PAX-20260310-7415.

Run on server:
  docker exec towt-app-v2 python3 /app/migrations/purge_passengers_except_7415.py
"""
import asyncio
from app.database import engine
from sqlalchemy import text


async def purge():
    async with engine.begin() as conn:
        total = (await conn.execute(text("SELECT COUNT(*) FROM passenger_bookings"))).scalar()
        keep = (await conn.execute(text(
            "SELECT COUNT(*) FROM passenger_bookings WHERE reference = 'PAX-20260310-7415'"
        ))).scalar()
        print(f"Total bookings: {total}")
        print(f"Booking to keep (PAX-20260310-7415): {keep}")

        if not keep:
            print("WARNING: PAX-20260310-7415 not found! Aborting.")
            return

        result = await conn.execute(text(
            "DELETE FROM passenger_bookings WHERE reference != 'PAX-20260310-7415'"
        ))
        print(f"Deleted: {result.rowcount} bookings (cascades handle passengers, payments, docs, etc.)")

        remaining = (await conn.execute(text("SELECT COUNT(*) FROM passenger_bookings"))).scalar()
        pax = (await conn.execute(text("SELECT COUNT(*) FROM passengers"))).scalar()
        print(f"Remaining: {remaining} booking(s), {pax} passenger(s)")


asyncio.run(purge())
