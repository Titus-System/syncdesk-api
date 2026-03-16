#!/bin/sh
set -e

echo "⏳ Waiting for PostgreSQL to be ready..."
until python - <<'PY' 2>/dev/null
import asyncio
import os

import asyncpg


async def check_db() -> None:
  conn = await asyncpg.connect(
    host=os.environ["POSTGRES_HOST"],
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    database=os.environ["POSTGRES_DB"],
  )
  await conn.close()


asyncio.run(check_db())
PY
do
  echo "  postgres not ready yet, retrying in 2s..."
  sleep 2
done

echo "✅ PostgreSQL is ready."

echo "🔄 Running Alembic migrations..."
alembic upgrade head

echo "🚀 Starting FastAPI..."
if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
  exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
fi

exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
