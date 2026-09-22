import os
import asyncpg
import uuid
from typing import Optional

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres-svc:5432/postgres")

def _parse_args(args):
    parsed = []
    for arg in args:
        if isinstance(arg, str):
            try:
                # If the string is exactly 36 chars and conforms to UUID structure, parse it.
                # Avoid accidentally parsing small strings or normal text.
                if len(arg) == 36:
                    parsed.append(uuid.UUID(arg))
                    continue
            except ValueError:
                pass
        parsed.append(arg)
    return tuple(parsed)

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(DATABASE_URL)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def fetch_one(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *_parse_args(args))

    async def fetch_all(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *_parse_args(args))

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *_parse_args(args))

db = Database()
