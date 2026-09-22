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
            await self._init_schema()

    async def _init_schema(self):
        schema_sql = """
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        CREATE TABLE IF NOT EXISTS chats (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id VARCHAR(255) NOT NULL,
            title TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            chat_id UUID REFERENCES chats(id) ON DELETE CASCADE,
            role VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS files (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id VARCHAR(255),
            filename VARCHAR(255) NOT NULL,
            gcs_path TEXT NOT NULL,
            file_size_bytes BIGINT,
            content_type VARCHAR(100),
            uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_shared BOOLEAN DEFAULT FALSE
        );
        CREATE TABLE IF NOT EXISTS sensor_telemetry (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            domain VARCHAR(50) NOT NULL,
            sensor_id VARCHAR(100) NOT NULL,
            sector VARCHAR(50) DEFAULT 'Sector 9',
            threat_level VARCHAR(20) NOT NULL,
            latitude NUMERIC(10, 6),
            longitude NUMERIC(10, 6),
            title VARCHAR(255) NOT NULL,
            summary TEXT,
            raw_payload JSONB
        );
        CREATE TABLE IF NOT EXISTS military_units (
            unit_id VARCHAR(50) PRIMARY KEY,
            unit_name VARCHAR(150) NOT NULL,
            branch VARCHAR(50) NOT NULL,
            sector VARCHAR(50) NOT NULL,
            base_location VARCHAR(100) NOT NULL,
            readiness_rating VARCHAR(10) NOT NULL,
            commander VARCHAR(100) NOT NULL,
            personnel_count INT NOT NULL,
            operational_status VARCHAR(50) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS equipment_inventory (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            unit_id VARCHAR(50) REFERENCES military_units(unit_id) ON DELETE CASCADE,
            equipment_type VARCHAR(100) NOT NULL,
            total_assigned INT NOT NULL,
            operational_count INT NOT NULL,
            in_repair_count INT NOT NULL,
            readiness_percentage NUMERIC(5,2) GENERATED ALWAYS AS (ROUND((operational_count::NUMERIC / total_assigned::NUMERIC) * 100, 2)) STORED
        );
        CREATE TABLE IF NOT EXISTS fuel_and_supplies (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            base_location VARCHAR(100) NOT NULL,
            sector VARCHAR(50) NOT NULL,
            fuel_gallons_jp8 INT NOT NULL,
            days_of_supply INT NOT NULL,
            ammunition_pallets INT NOT NULL,
            medical_kits INT NOT NULL,
            resupply_status VARCHAR(50) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS convoy_routes (
            route_id VARCHAR(50) PRIMARY KEY,
            route_name VARCHAR(100) NOT NULL,
            sector VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL,
            threat_assessment TEXT,
            last_scouted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            chokepoints INT DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS intelligence_reports (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            report_id VARCHAR(100) UNIQUE NOT NULL,
            title VARCHAR(255) NOT NULL,
            classification VARCHAR(50) DEFAULT 'UNCLASSIFIED',
            sector VARCHAR(50) DEFAULT 'Sector 9',
            source_agency VARCHAR(100) NOT NULL,
            published_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            content TEXT NOT NULL,
            summary TEXT
        );
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(schema_sql)
        except Exception as e:
            print(f"Schema init notice: {e}")

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
