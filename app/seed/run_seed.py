import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.postgres.engine import async_session
from app.seed import seed


async def run() -> None:
    async with async_session() as db, db.begin():
        await seed.seed_roles(db)
        await seed.seed_permissions(db)
        await seed.seed_role_permissions(db)


if __name__ == "__main__":
    asyncio.run(run())
