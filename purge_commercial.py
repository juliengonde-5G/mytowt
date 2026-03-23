"""
One-shot script: supprime toutes les grilles tarifaires, offres et ordres de transport.
Usage: python purge_commercial.py
       OU via Docker: docker exec towt-app-v2 python3 purge_commercial.py
"""
import asyncio
from app.database import engine
from sqlalchemy import text


async def purge():
    async with engine.begin() as conn:
        # Supprimer dans l'ordre des FK (enfants d'abord)
        tables = [
            ("rate_offers", "Offres tarifaires"),
            ("rate_grid_lines", "Lignes de grilles"),
            ("rate_grids", "Grilles tarifaires"),
        ]
        for table, label in tables:
            result = await conn.execute(text(f"DELETE FROM {table}"))
            print(f"  ✓ {label} ({table}): {result.rowcount} enregistrement(s) supprimé(s)")

    print("\nTerminé.")


if __name__ == "__main__":
    print("Suppression des données commerciales (grilles + offres)...\n")
    asyncio.run(purge())
