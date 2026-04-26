# Logic & Legacy: High-Performance Postgres Engine
# Demonstrates async connection pooling, relational JOINS, JSONB analytics,
# and ultra-fast serialization using `orjson` for a Centralized Logging System.

import asyncio
import asyncpg
import orjson  # Rust-backed JSON library. Drastically faster than standard 'json'
import uuid
import random
from datetime import datetime, timezone, timedelta

# Database connection details
DB_DSN = "postgresql://postgres:supersecret@localhost:5432/logic_legacy_db"

async def init_db(pool):
    """
    Creates a normalized schema for a high-performance logging system.
    Demonstrates relationships (Foreign Keys) and advanced JSONB usage.
    """
    async with pool.acquire() as conn:
        # Table 1: The Services generating the logs (Relations)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                service_id UUID PRIMARY KEY,
                service_name VARCHAR(100) UNIQUE NOT NULL,
                owner_team VARCHAR(100) NOT NULL
            );
        """)

        # Table 2: The massively append-only Log Events table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS log_events (
                log_id UUID PRIMARY KEY,
                service_id UUID REFERENCES services(service_id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL,
                severity VARCHAR(10) NOT NULL,
                message TEXT,
                metadata JSONB NOT NULL
            );
        """)
        
        # --- SEED RELATIONAL DATA ---
        services = [
            (uuid.uuid4(), "auth-service", "security-team"),
            (uuid.uuid4(), "payment-gateway", "finance-team"),
            (uuid.uuid4(), "inventory-worker", "ops-team")
        ]
        
        # Use ON CONFLICT to make seeding idempotent
        await conn.executemany("""
            INSERT INTO services (service_id, service_name, owner_team)
            VALUES ($1, $2, $3)
            ON CONFLICT (service_name) DO NOTHING
        """, services)
        
        print("[SYSTEM] Relational Schema initialized & seeded.")
        return services

async def simulate_high_throughput_writes(pool, services, batch_size=10000):
    """
    Simulates a logging firehose. Uses asyncpg's binary protocol `executemany` 
    and `orjson` to achieve massive insert speeds.
    """
    events = []
    severities = ["INFO", "INFO", "INFO", "WARN", "ERROR", "FATAL"]
    
    # Pre-generate data to simulate incoming log stream
    for i in range(batch_size):
        service = random.choice(services)
        severity = random.choice(severities)
        
        # orjson.dumps returns bytes. We decode to string for Postgres JSONB insertion.
        # This is exponentially faster than standard json.dumps()
        metadata_bytes = orjson.dumps({
            "cpu_usage": random.randint(10, 99),
            "memory_mb": random.randint(100, 2048),
            "endpoint": "/api/checkout" if service[1] == "payment-gateway" else "/api/data",
            "latency_ms": random.randint(10, 500) if severity != "ERROR" else random.randint(2000, 5000)
        })
        
        events.append((
            uuid.uuid4(),
            service[0], # The Foreign Key
            datetime.now(timezone.utc) - timedelta(minutes=random.randint(0, 1440)), # Random time in last 24h
            severity,
            f"Automated log entry sequence {i}",
            metadata_bytes.decode('utf-8') 
        ))

    print(f"[SYSTEM] Initiating bulk insert of {batch_size} relational logs...")
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany("""
                INSERT INTO log_events (log_id, service_id, created_at, severity, message, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, events)
            
    print("[SYSTEM] Bulk write completed.")

async def run_complex_analytics(pool):
    """
    Demonstrates powerful SQL querying: JOINs, Aggregations, and JSONB extraction.
    """
    async with pool.acquire() as conn:
        print("\n--- ANALYTICS: ERROR FREQUENCY BY TEAM (RELATIONAL JOIN) ---")
        # 1. Join tables to map logs back to the owning team
        error_tracking_query = """
            SELECT s.owner_team, s.service_name, COUNT(l.log_id) as error_count
            FROM log_events l
            JOIN services s ON l.service_id = s.service_id
            WHERE l.severity IN ('ERROR', 'FATAL')
            GROUP BY s.owner_team, s.service_name
            ORDER BY error_count DESC;
        """
        error_records = await conn.fetch(error_tracking_query)
        for r in error_records:
            print(f"Team: {r['owner_team']:<15} | Service: {r['service_name']:<18} | Critical Errors: {r['error_count']}")


        print("\n--- ANALYTICS: LATENCY SPIKES (JSONB FILTERING) ---")
        # 2. Querying INSIDE the metadata JSONB field and casting types
        # We find requests where latency was > 2000ms
        slow_query = """
            SELECT s.service_name, l.created_at, l.metadata->>'latency_ms' as latency, l.metadata->>'endpoint' as endpoint
            FROM log_events l
            JOIN services s ON l.service_id = s.service_id
            WHERE (l.metadata->>'latency_ms')::int > 2000
            ORDER BY (l.metadata->>'latency_ms')::int DESC
            LIMIT 5;
        """
        slow_records = await conn.fetch(slow_query)
        for r in slow_records:
            print(f"Service: {r['service_name']:<18} | Endpoint: {r['endpoint']:<15} | Latency: {r['latency']}ms")

async def main():
    # A single connection blocks. A pool allows hundreds of async workers to borrow connections.
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=5, max_size=20)
    
    try:
        # 1. Setup Relational Schema
        services = await init_db(pool)
        
        # 2. Simulate heavy write workload
        await simulate_high_throughput_writes(pool, services, batch_size=10000)
        
        # 3. Perform complex analytics across relations and JSONB
        await run_complex_analytics(pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    # Note: Requires a running Postgres instance.
    # Run via: asyncio.run(main())
    pass
