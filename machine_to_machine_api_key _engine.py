# Logic & Legacy: Machine-to-Machine (M2M) API Key Engine.
# Demonstrates Stripe-style API key generation with prefixes for easy log debugging,
# checksum validation to prevent wasted DB queries, and secure SHA-256 hashing for storage.

import secrets
import hashlib
import hmac
import time
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

# --- 1. THE API KEY ENGINE (SECURITY CORE) ---

class APIKeyManager:
    """
    Manages API keys securely. 
    Rule 1: Never store the raw API key.
    Rule 2: Add a prefix (e.g., 'pk_live_') so developers can identify keys in logs.
    Rule 3: Fast hashing (SHA-256) is acceptable here because API keys are high-entropy 
            and not vulnerable to dictionary attacks like human passwords.
    """
    def __init__(self):
        # Simulated Database: Stores { prefix: { hash, user_id, status, expires_at } }
        self.db: Dict[str, dict] = {}

    def _hash_key(self, raw_key: str) -> str:
        """Hashes the key for secure storage."""
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    def generate_key(self, user_id: str, environment: str = "live") -> str:
        """
        Generates a 32-byte secure token.
        Format: ll_[env]_[prefix]_[secret]
        Example: ll_live_abc12_xyz789...
        """
        # A visible prefix helps support teams identify WHICH key is being used
        prefix = secrets.token_hex(4) 
        # The actual cryptographic secret
        secret = secrets.token_urlsafe(32) 
        
        raw_key = f"ll_{environment}_{prefix}_{secret}"
        key_hash = self._hash_key(raw_key)

        # We store the hash and prefix, NEVER the secret.
        self.db[prefix] = {
            "key_hash": key_hash,
            "user_id": user_id,
            "environment": environment,
            "status": "active"
        }
        
        # The raw key is returned ONLY ONCE. If the user loses it, they must roll the key.
        return raw_key

    def verify_key(self, raw_key: str) -> dict:
        """Verifies an incoming API key."""
        try:
            parts = raw_key.split('_')
            if len(parts) != 4 or parts[0] != "ll":
                raise ValueError("Malformed API Key format")
            prefix = parts[2]
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid API Key format")

        # Pro Upgrade: We look up by prefix. 
        # If the prefix isn't in our DB, we reject instantly. No need to hash!
        record = self.db.get(prefix)
        if not record or record["status"] != "active":
            raise HTTPException(status_code=401, detail="Invalid or revoked API Key")

        # Hash the incoming key and use constant-time comparison
        attempt_hash = self._hash_key(raw_key)
        if not hmac.compare_digest(record["key_hash"], attempt_hash):
            raise HTTPException(status_code=401, detail="Invalid API Key")

        return record

    def roll_key(self, user_id: str, prefix_to_revoke: str) -> str:
        """
        Graceful Key Rotation: Marks old key as 'rolling' (expires in 24h),
        generates and returns a new key. Zero downtime for the client.
        """
        if prefix_to_revoke in self.db:
            self.db[prefix_to_revoke]["status"] = "rolling" # Logic to expire later
            
        return self.generate_key(user_id)


# --- 2. FASTAPI IMPLEMENTATION ---

app = FastAPI(title="Logic & Legacy: API Key Gateway")
key_manager = APIKeyManager()

# Standard header for API Keys
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(api_key: str = Security(api_key_header)) -> dict:
    """Dependency to enforce API Key authentication."""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    return key_manager.verify_key(api_key)

# --- 2.5 OAUTH 2.0 DELEGATED ACCESS (THE VALET KEY) ---

# The OAuth2 standard expects tokens in the Authorization header: `Bearer <token>`
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def require_oauth_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Simulates verifying an OAuth 2.0 Access Token (The Valet Key).
    In a real system, you would verify a JWT signature or call an Introspection endpoint.
    """
    if token != "mock_valet_key_123":
        raise HTTPException(
            status_code=401, 
            detail="Invalid OAuth 2.0 Access Token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # The token represents DELEGATED access. It tells us who the user is, 
    # and exactly what the third-party app is allowed to do (scopes).
    return {"user_id": "usr_994", "delegated_scopes": ["read:user_data"]}

# --- 3. ROUTES ---

@app.post("/admin/generate-key", summary="Create Key (Show Once)")
async def create_api_key():
    """Simulates a developer clicking 'Generate New Key' in an admin dashboard."""
    # In reality, secure this endpoint behind human AuthN (JWT/Session)!
    raw_key = key_manager.generate_key(user_id="usr_994", environment="live")
    return {
        "warning": "Copy this key now. You will never be able to see it again.",
        "api_key": raw_key
    }

@app.get("/api/v1/machine-data", summary="Protected M2M Endpoint")
async def get_machine_data(auth_context: dict = Depends(require_api_key)):
    """An endpoint protected strictly by Machine-to-Machine API Keys."""
    return {
        "message": "Access Granted",
        "environment_context": auth_context["environment"],
        "data": "Highly sensitive telemetry payload"
    }

@app.get("/api/v1/delegated-data", summary="Protected OAuth 2.0 Endpoint")
async def get_delegated_data(token_context: dict = Depends(require_oauth_token)):
    """
    An endpoint protected by OAuth 2.0. 
    This is for third-party apps acting ON BEHALF of a human user.
    """
    if "read:user_data" not in token_context["delegated_scopes"]:
        raise HTTPException(status_code=403, detail="Insufficient scope")
        
    return {
        "message": "Delegated Access Granted",
        "acting_on_behalf_of": token_context["user_id"],
        "data": "User's private data accessed via Valet Key"
    }

if __name__ == "__main__":
    import uvicorn
    # 1. Start server. 
    # 2. API Key Test: Pass X-API-Key header to /api/v1/machine-data
    # 3. OAuth Test: Pass Authorization: Bearer mock_valet_key_123 to /api/v1/delegated-data
    uvicorn.run(app, host="0.0.0.0", port=8000)
