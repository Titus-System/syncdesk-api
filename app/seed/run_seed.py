import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.mongo.db import mongo_db
from app.db.postgres.engine import async_session
from app.seed import seed
from app.seed.seed_examples import (
    seed_example_attendances,
    seed_example_conversations,
    seed_example_tickets,
    seed_example_user_roles,
    seed_example_users,
)


async def run() -> None:
    # --- Postgres ---
    async with async_session() as db, db.begin():
        await seed.seed_roles(db)
        await seed.seed_permissions(db)
        await seed.seed_role_permissions(db)
        await seed.seed_users(db)
        await seed_example_users(db)
        await seed_example_user_roles(db)

    # --- MongoDB ---
    await mongo_db.connect()
    try:
        mongo = mongo_db.get_db()
        await seed_example_attendances(mongo)
        await seed_example_tickets(mongo)
        await seed_example_conversations(mongo)
    finally:
        await mongo_db.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
