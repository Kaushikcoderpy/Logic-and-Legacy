# Logic & Legacy: The B-Tree & Query Planner Engine
# Demonstrates how the PostgreSQL Query Optimizer physical executes queries.
# We generate 1 million rows and run EXPLAIN ANALYZE to prove how Cardinality, 
# Composite Indexes, and Covering Indexes dictate read performance.

import asyncio
import asyncpg
import random

DB_DSN = "postgresql://postgres:supersecret@localhost:5432/logic_legacy_db"

async def setup_massive_table(pool):
    """Creates a table and fills it with 1 Million rows to force the Query Planner to think."""
    async with pool.acquire() as conn:
        print("[SYSTEM] Building massive 'users' table (1M rows)... this takes a moment.")
        await conn.execute("DROP TABLE IF EXISTS users CASCADE;")
        await conn.execute("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                tenant_id INT NOT NULL,
                status VARCHAR(20) NOT NULL,
                last_login TIMESTAMPTZ NOT NULL,
                email VARCHAR(255) NOT NULL
            );
        """)
        
        # Insert 1 Million rows using Postgres' generate_series for extreme speed
        await conn.execute("""
            INSERT INTO users (tenant_id, status, last_login, email)
            SELECT 
                trunc(random() * 1000 + 1), 
                CASE WHEN random() < 0.1 THEN 'banned' ELSE 'active' END,
                NOW() - (random() * (INTERVAL '365 days')),
                'user_' || gen || '@example.com'
            FROM generate_series(1, 1000000) as gen;
        """)
        print("[SYSTEM] 1 Million rows inserted.")

async def run_explain(conn, query_name, query):
    """Runs EXPLAIN ANALYZE and formats the output."""
    print(f"\n--- {query_name.upper()} ---")
    print(f"QUERY: {query}")
    # EXPLAIN ANALYZE actually runs the query and returns execution metrics
    explain_result = await conn.fetch(f"EXPLAIN ANALYZE {query}")
    for row in explain_result:
        print(row['QUERY PLAN'])

async def simulate_query_planner(pool):
    """
    Executes different indexing strategies and analyzes the Query Planner's decisions.
    """
    async with pool.acquire() as conn:
        
        # SCENARIO 1: The Table Scan (No Index)
        # Because we have no index on tenant_id, Postgres must read all 1,000,000 rows.
        await run_explain(conn, "Scenario 1: Full Table Scan", 
                          "SELECT id, email FROM users WHERE tenant_id = 450;")

        # Create a basic B-Tree index
        print("\n[SYSTEM] Creating B-Tree Index on tenant_id...")
        await conn.execute("CREATE INDEX idx_users_tenant ON users(tenant_id);")
        # Run ANALYZE to update database statistics so the planner knows about the index
        await conn.execute("ANALYZE users;")

        # SCENARIO 2: The Index Scan (B-Tree traversal)
        # Now, Postgres traverses the B-Tree (O(log n)), finds the pointer, and jumps to the disk.
        await run_explain(conn, "Scenario 2: Index Scan", 
                          "SELECT id, email FROM users WHERE tenant_id = 450;")

        # SCENARIO 3: The Cardinality Trap (Low Selectivity)
        # 90% of our users are 'active'. If we index the 'status' column and search for 'active', 
        # the Optimizer realizes traversing the index for 900,000 rows is slower than just scanning the table.
        print("\n[SYSTEM] Creating Low-Cardinality Index on status...")
        await conn.execute("CREATE INDEX idx_users_status ON users(status);")
        await conn.execute("ANALYZE users;")
        
        await run_explain(conn, "Scenario 3: The Optimizer Ignores Your Index (Table Scan)", 
                          "SELECT id, email FROM users WHERE status = 'active';")

        # SCENARIO 4: The Covering Index (Index-Only Scan)
        # We want to get the 'last_login' for a specific tenant.
        # If we include 'last_login' IN the index itself, Postgres never has to visit the main table!
        print("\n[SYSTEM] Creating Covering (Composite) Index...")
        await conn.execute("CREATE INDEX idx_users_tenant_login ON users(tenant_id, last_login);")
        await conn.execute("ANALYZE users;")
        
        await run_explain(conn, "Scenario 4: Index-Only Scan (The Holy Grail)", 
                          "SELECT tenant_id, last_login FROM users WHERE tenant_id = 450;")

async def main():
    pool = await asyncpg.create_pool(dsn=DB_DSN)
    try:
        await setup_massive_table(pool)
        await simulate_query_planner(pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    # asyncio.run(main())
    pass
