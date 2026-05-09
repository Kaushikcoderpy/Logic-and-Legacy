# Logic & Legacy: The Cursor Pagination Engine
# We build a raw SQLite + FastAPI server to mathematically prove that 
# OFFSET pagination scales in O(N) time and destroys databases, while 
# CURSOR pagination scales in O(1) time and handles infinite data instantly.
#
# Requires: pip install fastapi uvicorn sqlite3

import sqlite3
import time
from fastapi import FastAPI, Query

# ==========================================
# 1. DATABASE SETUP (1 Million Rows)
# ==========================================
DB_NAME = "legacy_data.db"

def seed_database():
    """Builds a database with 1 million rows and an indexed ID column."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, amount REAL)")
    
    # Check if already seeded to save time on restarts
    cursor.execute("SELECT COUNT(*) FROM transactions")
    if cursor.fetchone()[0] == 0:
        print("[SYSTEM] Generating 1,000,000 rows. This takes about 3 seconds...")
        # Bulk insert for speed
        rows = [(i, i * 1.5) for i in range(1, 1000001)]
        cursor.executemany("INSERT INTO transactions (id, amount) VALUES (?, ?)", rows)
        conn.commit()
        print("[SYSTEM] Database seeded. B-Tree index automatically created on PRIMARY KEY.")
    
    conn.close()

# ==========================================
# 2. FASTAPI SERVER
# ==========================================
app = FastAPI()

def get_db_connection():
    # SQLite requires check_same_thread=False for async frameworks
    return sqlite3.connect(DB_NAME, check_same_thread=False)

@app.on_event("startup")
def startup_event():
    seed_database()


@app.get("/api/v1/offset")
def fetch_via_offset(page: int = Query(1, ge=1)):
    """
    The Amateur Way.
    If the user requests page 20,000, we skip 999,950 rows.
    The database must physically read and discard all 999,950 rows.
    """
    limit = 50
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    start = time.perf_counter()
    # 🚨 THE DATABASE KILLER: OFFSET
    cursor.execute("SELECT * FROM transactions ORDER BY id ASC LIMIT ? OFFSET ?", (limit, offset))
    data = cursor.fetchall()
    duration = (time.perf_counter() - start) * 1000
    
    conn.close()
    
    return {
        "method": "OFFSET",
        "page_requested": page,
        "rows_skipped": offset,
        "execution_time_ms": round(duration, 2),
        "data_preview": data[:2]
    }


@app.get("/api/v1/cursor")
def fetch_via_cursor(last_id: int = Query(0, ge=0)):
    """
    The Architect Way.
    We don't skip rows. We use the B-Tree index to jump instantly to 'last_id'.
    Execution time is identical whether we are at row 50 or row 900,000.
    """
    limit = 50
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    start = time.perf_counter()
    # ✅ THE B-TREE JUMP: WHERE id > ?
    cursor.execute("SELECT * FROM transactions WHERE id > ? ORDER BY id ASC LIMIT ?", (last_id, limit))
    data = cursor.fetchall()
    duration = (time.perf_counter() - start) * 1000
    
    conn.close()
    
    # Calculate the cursor for the next API call
    next_cursor = data[-1][0] if data else None
    
    return {
        "method": "CURSOR",
        "last_id_provided": last_id,
        "next_cursor_to_use": next_cursor,
        "execution_time_ms": round(duration, 2),
        "data_preview": data[:2]
    }


# ==========================================
# EXECUTION INSTRUCTIONS
# ==========================================
"""
Run this server:
uvicorn pagination_engine:app --reload

Test 1: The Fast Offset (Page 1)
Open: http://127.0.0.1:8000/api/v1/offset?page=1
Time: ~0.1 ms (Very fast, it skips nothing)

Test 2: The Slow Offset (Page 20,000)
Open: http://127.0.0.1:8000/api/v1/offset?page=20000
Time: ~15.0 ms (It had to read and discard 1 million rows to get your 50)

Test 3: The Cursor Jump (Deep Data)
Open: http://127.0.0.1:8000/api/v1/cursor?last_id=999950
Time: ~0.1 ms (Instant. It used the B-Tree index to teleport straight to the row)
"""
if __name__ == "__main__":
    pass
