# Logic & Legacy: The Stateless Deception (JWTs & HttpOnly Cookies).
# Demonstrates how to manually construct, sign, and verify a JWT without using `pyjwt`.
# Implements the Hybrid Safe Approach: Storing JWTs in secure, HttpOnly cookies.

import json
import base64
import hmac
import hashlib
import time
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException, Response, Request, Depends, status

# --- 1. CORE JWT ENGINE (NO PYJWT) ---

class RawJWTEngine:
    """
    Constructs and verifies JSON Web Tokens from scratch to prove how the math works.
    JWTs are NOT encrypted. They are just base64 encoded JSON, cryptographically signed.
    """
    def __init__(self, secret_key: str):
        # In production, this must be a highly secure, randomly generated string loaded from ENV.
        self.secret_key = secret_key.encode('utf-8')

    def _base64url_encode(self, data: bytes) -> str:
        """Removes padding (=) to conform to the JWT standard."""
        return base64.urlsafe_b64encode(data).decode('utf-8').rstrip("=")

    def _base64url_decode(self, b64_string: str) -> bytes:
        """Adds padding back to decode correctly."""
        padding_needed = 4 - (len(b64_string) % 4)
        if padding_needed and padding_needed != 4:
            b64_string += "=" * padding_needed
        return base64.urlsafe_b64decode(b64_string)

    def _sign(self, header_b64: str, payload_b64: str) -> str:
        """Creates the HMAC-SHA256 signature."""
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        signature = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        return self._base64url_encode(signature)

    def create_token(self, payload: dict, expiration_minutes: int = 15) -> str:
        """Constructs the standard Header.Payload.Signature JWT format."""
        # 1. Header (Always the same for standard HMAC-SHA256)
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = self._base64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
        
        # 2. Payload (Add expiration claim 'exp')
        payload["exp"] = int(time.time()) + (expiration_minutes * 60)
        payload["iat"] = int(time.time()) # Issued at
        payload_b64 = self._base64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        
        # 3. Signature
        signature_b64 = self._sign(header_b64, payload_b64)
        
        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def verify_token(self, token: str) -> dict:
        """Parses the JWT, verifies the math, and checks expiration."""
        try:
            header_b64, payload_b64, signature_b64 = token.split(".")
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed token format")

        # 1. Verify Signature (Math Check)
        expected_signature = self._sign(header_b64, payload_b64)
        if not hmac.compare_digest(expected_signature, signature_b64):
            raise HTTPException(status_code=401, detail="Signature tampering detected")

        # 2. Decode Payload
        try:
            payload_json = self._base64url_decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
        except Exception:
            raise HTTPException(status_code=401, detail="Failed to decode payload")

        # 3. Verify Expiration
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Token has expired")

        return payload


# --- 2. FASTAPI IMPLEMENTATION: THE HYBRID COOKIE APPROACH ---

app = FastAPI(title="Logic & Legacy: JWT & Cookie Architecture")
jwt_engine = RawJWTEngine(secret_key="SuperSecretArchitectureKeyDoNotShare!")

# --- AUTHENTICATION DEPENDENCY ---
def verify_hybrid_session(request: Request) -> dict:
    """
    Extracts the JWT from the HttpOnly cookie, NOT the Authorization header.
    This protects against XSS (Cross-Site Scripting) attacks extracting tokens from LocalStorage.
    """
    token = request.cookies.get("ll_session_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Session cookie missing"
        )
    
    return jwt_engine.verify_token(token)


# --- ROUTES ---

@app.post("/api/v1/auth/login", summary="Login & Set HttpOnly Cookie")
async def login(response: Response):
    """
    Simulates a successful login. 
    Instead of returning the JWT in the JSON body, we attach it to a secure Cookie.
    """
    # 1. Generate the JWT Payload
    user_data = {"user_id": "usr_994", "role": "admin"}
    token = jwt_engine.create_token(user_data, expiration_minutes=15)
    
    # 2. THE FIX: Set the HttpOnly Cookie.
    # HttpOnly=True ensures JavaScript (and thus XSS attacks) CANNOT read this cookie.
    # Secure=True ensures it only transmits over HTTPS.
    # SameSite='lax' prevents basic CSRF attacks.
    response.set_cookie(
        key="ll_session_token",
        value=token,
        httponly=True, 
        secure=True,    # Set to False ONLY if testing on localhost without HTTPS
        samesite="lax",
        max_age=15 * 60 # 15 minutes
    )
    
    return {"message": "Login successful. Secure cookie set."}

@app.get("/api/v1/users/me", summary="Read Profile (Protected)")
async def get_profile(user: dict = Depends(verify_hybrid_session)):
    """
    The browser automatically sends the HttpOnly cookie with this request.
    The dependency verifies the JWT signature mathematically without touching a DB.
    """
    return {
        "message": "Access Granted",
        "user_data": user,
        "note": "Notice how we didn't query a database to know who you are."
    }

@app.post("/api/v1/auth/logout", summary="Logout & Destroy Cookie")
async def logout(response: Response):
    """
    JWT Revocation problem: You can't mathematically 'un-sign' a token.
    The easiest immediate fix on the client side is instructing the browser to delete the cookie.
    (Note: If the token was stolen before this, it remains mathematically valid until expiration).
    """
    response.delete_cookie("ll_session_token", httponly=True, samesite="lax")
    return {"message": "Logged out. Cookie destroyed."}


if __name__ == "__main__":
    import uvicorn
    # Test via browser or Postman (Postman handles cookies automatically).
    uvicorn.run(app, host="0.0.0.0", port=8000)
