import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

import aiosqlite
from fastapi import FastAPI, HTTPException, Header, Query, Path, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# HERE YOU CAN READ BREAKDOWN OF THE BLOG : https://logicandlegacy.blogspot.com/2026/04/the-reality-of-api-routing-http-intents.html
# --- CONFIG & LIFESPAN ---
DB_FILE = "logic_legacy_production.db"

async def init_db():
    """Idempotent schema creation. Sets up persistent state for our routes."""
    async with aiosqlite.connect(DB_FILE) as db:
        # Core entity table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                status TEXT NOT NULL,
                content_length INTEGER DEFAULT 0
            )
        """)
        # Idempotency store to survive application restarts
        await db.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key_hash TEXT PRIMARY KEY,
                status_code INTEGER,
                response_payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Provision DB
    await init_db()
    yield
    # Shutdown: Clean up resources if needed (connections auto-close contextually here)

app = FastAPI(
    title="Logic & Legacy: Production Routing",
    description="Demonstrating strict route priority, DB-backed idempotency, and async background execution.",
    lifespan=lifespan
)

# --- DEPENDENCIES ---
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yields a database connection per request, ensuring clean closure."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        yield db

# --- SCHEMAS ---
class DocumentCreate(BaseModel):
    title: str = Field(..., example="Designing Data-Intensive Applications")
    author: str = Field(..., example="Martin Kleppmann")
    raw_text: str = Field(..., example="Very long book content...")

class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None

# --- BACKGROUND WORKERS ---
async def process_document_background(doc_id: str, raw_text: str):
    """
    Simulates a heavy CPU/IO bound task (like OCR, embedding generation, or NLP).
    Crucial: This runs OUTSIDE the request/response cycle to prevent event loop blocking.
    """
    # Simulate heavy processing (e.g., chunking text, calling AI models)
    await asyncio.sleep(3) 
    calculated_length = len(raw_text)
    
    # Update DB state upon completion
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE documents SET status = 'PROCESSED', content_length = ? WHERE id = ?",
            (calculated_length, doc_id)
        )
        await db.commit()

# --- ROUTING EXAMPLES ---

# 🚨 THE COLLISION TRAP (Static before Dynamic)
# If placed below the {doc_id} route, "export" would be parsed as a UUID and crash.
@app.get("/api/v1/documents/export", summary="STATIC ROUTE: Export all system data")
async def export_documents(db: aiosqlite.Connection = Depends(get_db)):
    """Downloads all documents. Notice this static path is safely registered first."""
    async with db.execute("SELECT * FROM documents") as cursor:
        rows = await cursor.fetchall()
        return {"exported_records": len(rows), "data": [dict(r) for r in rows]}

# DYNAMIC GET
@app.get("/api/v1/documents/{doc_id}", summary="DYNAMIC ROUTE: Read a specific resource")
async def get_document(
    doc_id: str = Path(..., description="UUID of the document"),
    db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        return dict(row)


# IDEMPOTENT POST WITH BACKGROUND TASK
@app.post("/api/v1/documents", status_code=201, summary="CREATE with Idempotency Guard")
async def create_document(
    payload: DocumentCreate,
    bg_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
    idempotency_key: str = Header(..., description="UUID supplied by client to prevent double-charges")
):
    """
    Production POST: 
    1. Checks persistent DB for the Idempotency Key.
    2. If exists, returns the exact cached JSON response (status 201 or whatever it was).
    3. If new, inserts to DB, schedules background work, and caches the response.
    """
    # 1. Check idempotency store
    async with db.execute("SELECT * FROM idempotency_keys WHERE key_hash = ?", (idempotency_key,)) as cursor:
        existing_tx = await cursor.fetchone()
        if existing_tx:
            # Short-circuit and return cached response directly
            return JSONResponse(
                status_code=existing_tx["status_code"],
                content=json.loads(existing_tx["response_payload"])
            )

    # 2. Process new transaction
    new_doc_id = str(uuid.uuid4())
    
    await db.execute(
        "INSERT INTO documents (id, title, author, status) VALUES (?, ?, ?, ?)",
        (new_doc_id, payload.title, payload.author, "PENDING")
    )
    
    # 3. Offload heavy lifting to unblock the HTTP response
    bg_tasks.add_task(process_document_background, new_doc_id, payload.raw_text)
    
    # Construct response
    response_data = {
        "message": "Document accepted for processing",
        "document_id": new_doc_id,
        "status": "PENDING"
    }

    # 4. Save idempotency state IN THE SAME SCOPE
    await db.execute(
        "INSERT INTO idempotency_keys (key_hash, status_code, response_payload) VALUES (?, ?, ?)",
        (idempotency_key, 201, json.dumps(response_data))
    )
    await db.commit()

    return response_data

# SEMANTIC PATCH
@app.patch("/api/v1/documents/{doc_id}", summary="PARTIAL UPDATE resource")
async def update_document(
    doc_id: str, 
    updates: DocumentUpdate,
    db: aiosqlite.Connection = Depends(get_db)
):
    # Filter out unset fields (Pydantic's exclude_unset is vital here)
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields provided for update")

    # Dynamic query building for real partial updates
    set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
    values = list(update_data.values())
    values.append(doc_id)

    query = f"UPDATE documents SET {set_clause} WHERE id = ?"
    
    cursor = await db.execute(query, values)
    await db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"message": f"Document {doc_id} successfully patched"}

# IDEMPOTENT DELETE
@app.delete("/api/v1/documents/{doc_id}", status_code=204, summary="Idempotent Removal")
async def delete_document(doc_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """
    A true REST DELETE is idempotent. If the client retries a DELETE that already succeeded,
    we do NOT throw a 404. We gracefully return 204 No Content.
    """
    await db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await db.commit()
    # Return 204 regardless of whether rows were actually deleted
    return 

if __name__ == "__main__":
    import uvicorn
    # To run: python api_routing_architecture.py
    uvicorn.run(app, host="0.0.0.0", port=8000)
