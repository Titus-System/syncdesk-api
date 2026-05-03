import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.mongo.db import mongo_db
from app.db.postgres.engine import async_session
from app.seed import seed
from app.seed.seed_examples import (
    seed_example_attendances,
    seed_example_companies_and_products,
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
        
        # Agora as empresas/produtos são inseridas ANTES dos usuários (foreign key constraint)
        await seed_example_companies_and_products(db)
        await seed.seed_users(db)
        
        # Descomentado:
        await seed_example_users(db)
        await seed_example_user_roles(db)

    # --- MongoDB ---
    await mongo_db.connect()
    try:
        mongo = mongo_db.get_db()
        # Descomentado (opcional, para uma base de testes rica no mongo):
        await seed_example_attendances(mongo)
        await seed_example_tickets(mongo)
        await seed_example_conversations(mongo)
    finally:
        await mongo_db.disconnect()


if __name__ == "__main__":
    asyncio.run(run())