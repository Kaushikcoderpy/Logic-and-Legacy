# Logic & Legacy: Production RBAC & Secure Auth Pipeline.
# Demonstrates timing-attack mitigation during login, real session management, 
# and dynamic Role/Permission assignment at the time of user registration.

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel

DB_FILE = "logic_legacy_production_auth.db"

# Security Context for Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# DUMMY_HASH to mitigate timing attacks on invalid usernames
DUMMY_HASH = pwd_context.hash("dummy_password_for_timing_mitigation")

# FastAPI OAuth2 scheme (extracts token from Authorization: Bearer <token>)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# --- LIFESPAN & BOOTSTRAP (REAL WORLD APPROACH) ---
async def bootstrap_system():
    """
    Creates schemas and ONLY bootstraps the foundational architecture:
    The standard roles, the system permissions, and the root Admin account.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS permissions (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id TEXT,
                permission_id TEXT,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES roles (id),
                FOREIGN KEY (permission_id) REFERENCES permissions (id)
            );
            
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role_id TEXT,
                FOREIGN KEY (role_id) REFERENCES roles (id)
            );
            
            -- Stateful sessions (We cover stateless JWTs tomorrow)
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)
        
        # 1. System Permissions Bootstrap
        await db.executescript("""
            INSERT OR IGNORE INTO permissions (id, name) VALUES 
            ('p_read', 'article:read'),
            ('p_write', 'article:write'),
            ('p_delete', 'article:delete');
        """)
        
        # 2. System Roles Bootstrap
        await db.executescript("""
            INSERT OR IGNORE INTO roles (id, name) VALUES 
            ('r_admin', 'Admin'),
            ('r_writer', 'Writer'),
            ('r_reader', 'Reader');
        """)
        
        # 3. Map Permissions to Roles
        await db.executescript("""
            INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES 
            ('r_admin', 'p_read'), ('r_admin', 'p_write'), ('r_admin', 'p_delete'),
            ('r_writer', 'p_read'), ('r_writer', 'p_write'),
            ('r_reader', 'p_read');
        """)
        
        # 4. Bootstrap ONLY the Super Admin (Real systems require an initial owner)
        admin_hash = pwd_context.hash("SuperSecretAdminPass123!")
        try:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role_id) VALUES (?, ?, ?, ?)",
                ('u_root_001', 'admin', admin_hash, 'r_admin')
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            pass # Admin already exists

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bootstrap_system()
    yield

app = FastAPI(title="Logic & Legacy: Auth Gatekeeper", lifespan=lifespan)

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        yield db

# --- SCHEMAS ---
class UserRegistration(BaseModel):
    username: str
    password: str
    role_name: str  # e.g., "Writer" or "Reader"

# --- AUTHENTICATION PIPELINE (AuthN) ---

@app.post("/api/v1/auth/register", status_code=201, summary="Register & Assign Role")
async def register_user(payload: UserRegistration, db: aiosqlite.Connection = Depends(get_db)):
    """
    Registers a new user and dynamically assigns their initial Role (and thus permissions).
    In production, you would restrict who can request the 'Admin' role.
    """
    # 1. Lookup the requested role to get its ID
    async with db.execute("SELECT id FROM roles WHERE name = ?", (payload.role_name,)) as cursor:
        role = await cursor.fetchone()
        if not role:
            raise HTTPException(status_code=400, detail="Invalid role requested.")
            
    # 2. Hash password and save user
    hashed_pwd = pwd_context.hash(payload.password)
    user_id = f"u_{secrets.token_hex(4)}"
    
    try:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role_id) VALUES (?, ?, ?, ?)",
            (user_id, payload.username, hashed_pwd, role["id"])
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        # Prevent user enumeration on registration by being vague, or handle cleanly
        raise HTTPException(status_code=400, detail="Username already taken.")

    return {"message": "Account created successfully. Role assigned.", "user_id": user_id}

@app.post("/api/v1/auth/login", summary="Login with Timing Attack Defense")
async def login(credentials: OAuth2PasswordRequestForm = Depends(), db: aiosqlite.Connection = Depends(get_db)):
    """Authenticates a user, securely handling missing users to prevent timing leaks."""
    async with db.execute("SELECT id, password_hash FROM users WHERE username = ?", (credentials.username,)) as cursor:
        user = await cursor.fetchone()
        
    if not user:
        # TIMING ATTACK DEFENSE: Burn CPU cycles on a dummy hash so hackers 
        # can't use response times to map out valid usernames.
        pwd_context.verify(credentials.password, DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials", # Silent generic error
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not pwd_context.verify(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials", # Exact same error as above
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Generate secure session token
    session_token = secrets.token_urlsafe(32)
    await db.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (session_token, user["id"]))
    await db.commit()
    
    return {"access_token": session_token, "token_type": "bearer"}

async def get_current_user(token: str = Depends(oauth2_scheme), db: aiosqlite.Connection = Depends(get_db)):
    """Dependency to retrieve the logged-in user from the session token."""
    query = """
        SELECT u.id, u.username, u.role_id 
        FROM sessions s JOIN users u ON s.user_id = u.id 
        WHERE s.token = ?
    """
    async with db.execute(query, (token,)) as cursor:
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
        return user

# --- AUTHORIZATION PIPELINE (AuthZ) ---

class RequirePermission:
    """
    The RBAC Engine. Executes a single optimized query to verify if the 
    authenticated user's role contains the required permission.
    """
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self, 
        current_user: aiosqlite.Row = Depends(get_current_user),
        db: aiosqlite.Connection = Depends(get_db)
    ):
        query = """
            SELECT 1 FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = ? AND p.name = ?
        """
        async with db.execute(query, (current_user["role_id"], self.required_permission)) as cursor:
            has_permission = await cursor.fetchone()
            
            if not has_permission:
                # 403 Forbidden: Identity verified, but access denied.
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"RBAC Violation: Lacks '{self.required_permission}' scope."
                )
        return current_user

# --- BUSINESS LOGIC ENDPOINTS ---

@app.get("/api/v1/articles", summary="Read Articles (Readers, Writers, Admins)")
async def read_articles(user=Depends(RequirePermission("article:read"))):
    return {"data": ["Architecture Post 1", "Architecture Post 2"]}

@app.post("/api/v1/articles", summary="Write Articles (Writers, Admins)")
async def create_article(user=Depends(RequirePermission("article:write"))):
    return {"message": "Article published.", "author": user["username"]}

@app.delete("/api/v1/articles/{id}", summary="Delete Articles (Admins ONLY)")
async def delete_article(id: int, user=Depends(RequirePermission("article:delete"))):
    return {"message": f"Article {id} deleted permanently by admin {user['username']}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
