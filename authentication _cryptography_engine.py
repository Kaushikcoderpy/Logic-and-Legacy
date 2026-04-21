# Logic & Legacy: Authentication & Cryptography Engine.
# Demonstrates Elliptic Curve Cryptography (ECC) for token signing, 
# built-in scrypt for secure password hashing (avoiding external bloated libs),
# and the Pro Upgrade: Replay Attack Defense using nonce tracking.

import json
import time
import base64
import secrets
import hashlib
import os
from typing import Dict, Tuple

# The only external library required for military-grade asymmetric math in Python.
# Run: pip install cryptography
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature

# --- 1. THE HASHING FALLACY: PROPER PASSWORD STORAGE ---

class IdentityStore:
    """
    Handles identity verification safely.
    RULE: Passwords are hashed. Usernames/Emails are stored in PLAINTEXT (or symmetrically encrypted if PII).
    Never hash a username, because hashing is a destructive, one-way function.
    """
    def __init__(self):
        # In memory DB for demonstration
        self.db = {}

    def register_user(self, username: str, plain_password: str) -> str:
        # Scrypt is a memory-hard key derivation function, making it extremely resistant to GPU brute-forcing.
        # Parameter Breakdown for Tuning:
        # n (Cost): CPU/Memory cost. Must be a power of 2. Higher = exponentially harder (e.g., 65536 or 131072 in prod).
        # r (Block Size): The size of the memory blocks being manipulated. Standard is 8.
        # p (Parallelization): Number of independent threads required to compute. Standard is 1 for web APIs.
        # maxmem: Upper bound on memory usage (0 = use OpenSSL/Python defaults).
        salt = os.urandom(16)
        password_hash = hashlib.scrypt(
            plain_password.encode('utf-8'), 
            salt=salt, 
            n=16384, r=8, p=1, maxmem=0
        )
        
        user_id = f"usr_{secrets.token_hex(4)}"
        self.db[username] = {
            "id": user_id,
            "salt": base64.b64encode(salt).decode('utf-8'),
            "hash": base64.b64encode(password_hash).decode('utf-8')
        }
        return user_id

    def verify_password(self, username: str, plain_password: str) -> bool:
        record = self.db.get(username)
        if not record:
            return False # (Note: In a real API, mitigate timing attacks here as discussed in AuthZ)
            
        salt = base64.b64decode(record["salt"])
        expected_hash = base64.b64decode(record["hash"])
        
        # Must use the exact same cost parameters to recreate and verify the hash
        attempt_hash = hashlib.scrypt(
            plain_password.encode('utf-8'), 
            salt=salt, 
            n=16384, r=8, p=1, maxmem=0
        )
        # Use compare_digest to prevent timing attacks during hash comparison
        return secrets.compare_digest(expected_hash, attempt_hash)


# --- 2. ASYMMETRIC CRYPTOGRAPHY (ECC) & PRO UPGRADE (REPLAY DEFENSE) ---

class SecureTokenEngine:
    """
    Generates and verifies cryptographic tokens using ECC (SECP256R1).
    Includes Replay Attack mitigation via Nonce caching and TTL.
    """
    def __init__(self, ttl_seconds: int = 60):
        # 1. Generate SECP256R1 Keypair (256-bit ECC = 3072-bit RSA)
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        
        self.ttl_seconds = ttl_seconds
        
        # Simulated Redis Cache for Nonces.
        # In production, this MUST be a centralized cache like Redis with an EXPIRE command.
        self._nonce_cache: Dict[str, float] = {}

    def generate_token(self, payload: dict) -> str:
        """Signs a payload using the server's private ECC key and injects replay defenses."""
        # Inject Pro Upgrade defenses: Nonce & Timestamp
        payload["nonce"] = secrets.token_hex(16)
        payload["timestamp"] = int(time.time())
        
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        
        # Sign the payload bytes
        signature = self.private_key.sign(
            payload_bytes,
            ec.ECDSA(hashes.SHA256())
        )
        
        # Create a transport-friendly string: base64(payload).base64(signature)
        b64_payload = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip("=")
        b64_signature = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip("=")
        
        return f"{b64_payload}.{b64_signature}"

    def verify_token(self, token: str) -> dict:
        """
        Verifies the signature, checks TTL, and prevents Replay Attacks.
        Raises ValueError if any security check fails.
        """
        try:
            b64_payload, b64_signature = token.split(".")
            
            # Re-pad base64 strings
            payload_bytes = base64.urlsafe_b64decode(b64_payload + "==")
            signature_bytes = base64.urlsafe_b64decode(b64_signature + "==")
        except Exception:
            raise ValueError("Malformed token structure.")

        # 1. Verify Cryptographic Integrity (Math check)
        try:
            self.public_key.verify(
                signature_bytes,
                payload_bytes,
                ec.ECDSA(hashes.SHA256())
            )
        except InvalidSignature:
            raise ValueError("Invalid Signature: Payload was tampered with.")

        # 2. Parse Payload
        payload = json.loads(payload_bytes)
        
        # 3. Time-to-Live (TTL) Check
        token_time = payload.get("timestamp", 0)
        current_time = int(time.time())
        if current_time - token_time > self.ttl_seconds:
            raise ValueError("Token has expired.")

        # 4. PRO UPGRADE: Replay Attack Defense (Nonce Check)
        nonce = payload.get("nonce")
        if not nonce:
            raise ValueError("Missing security nonce.")
            
        # Clean up old nonces (Simulating Redis key expiration)
        self._nonce_cache = {k: v for k, v in self._nonce_cache.items() if current_time - v < self.ttl_seconds}
        
        if nonce in self._nonce_cache:
            raise ValueError("Replay Attack Detected: This exact token was already used.")
            
        # Store nonce to block future replay attempts within the TTL window
        self._nonce_cache[nonce] = current_time

        return payload

# --- 3. EXECUTION & ATTACK SIMULATIONS ---

if __name__ == "__main__":
    print("\n--- 🛡️ LOGIC & LEGACY: AUTH & CRYPTO ENGINE ---")
    
    # Setup
    store = IdentityStore()
    engine = SecureTokenEngine(ttl_seconds=60)
    
    # 1. Registration (Proper hashing)
    user_id = store.register_user("john_doe", "SuperSecret123!")
    print(f"[SYSTEM] User registered. Internal DB ID: {user_id}")
    
    # Validate Login
    is_valid = store.verify_password("john_doe", "SuperSecret123!")
    print(f"[SYSTEM] Password Verification: {is_valid}")
    
    # 2. Generate the ECC Signed Token
    raw_payload = {"user_id": user_id, "role": "writer", "action": "publish_article"}
    secure_token = engine.generate_token(raw_payload)
    print(f"\n[SYSTEM] Generated ECC Token:\n{secure_token}\n")
    
    # 3. Valid Consumption
    print("--- SCENARIO 1: Valid API Request ---")
    try:
        data = engine.verify_token(secure_token)
        print(f"✅ Success. Decoded secure data: {data}")
    except ValueError as e:
        print(f"❌ Failed: {e}")

    # 4. Pro Upgrade Simulation: Replay Attack
    print("\n--- SCENARIO 2: Replay Attack (Hacker intercepts and resends token) ---")
    try:
        # Hacker sends the exact same, mathematically valid token a second time
        data = engine.verify_token(secure_token)
        print(f"✅ Success. Decoded secure data: {data}")
    except ValueError as e:
        print(f"❌ REJECTED: {e}")

    # 5. Math Simulation: Tamper Attack
    print("\n--- SCENARIO 3: Tamper Attack (Hacker tries to escalate privileges) ---")
    try:
        # Hacker decodes the payload, changes role to 'admin', and re-encodes
        b64_payload, b64_signature = secure_token.split(".")
        payload_bytes = base64.urlsafe_b64decode(b64_payload + "==")
        hacked_payload = json.loads(payload_bytes)
        
        hacked_payload["role"] = "admin" # Privilege escalation!
        
        hacked_bytes = json.dumps(hacked_payload, separators=(',', ':')).encode('utf-8')
        hacked_b64 = base64.urlsafe_b64encode(hacked_bytes).decode('utf-8').rstrip("=")
        
        forged_token = f"{hacked_b64}.{b64_signature}"
        
        # Send forged token to server
        engine.verify_token(forged_token)
        print("✅ Success. (THIS SHOULD NOT HAPPEN)")
    except ValueError as e:
        print(f"❌ REJECTED: {e}")
    
    print("\n------------------------------------------------")
