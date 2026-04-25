# Logic & Legacy: OpenID Connect (OIDC) Federation Engine.
# Demonstrates how a Relying Party (your app) cryptographically verifies an ID Token
# issued by an external Identity Provider (IdP) like Google, Auth0, or Okta.
# Crucially: We dynamically fetch the IdP's public keys from their JWKS endpoint.

import asyncio
import jwt  # We use PyJWT here because fetching & parsing JWKS manually is reinventing the wheel
from fastapi import FastAPI, HTTPException, Depends, Header
import httpx

# --- 1. FEDERATION INFRASTRUCTURE ---

class OIDCFederationEngine:
    """
    Handles decentralized cryptographic trust.
    Instead of checking our own database for a user, we ask:
    'Did Google actually sign this ID Token, and has it expired?'
    """
    def __init__(self, issuer_url: str, audience: str):
        # 1. The Issuer (Who claimed to create the token?) E.g., 'https://accounts.google.com'
        self.issuer_url = issuer_url
        
        # 2. The Audience (Who was this token minted for?) E.g., Your specific Google Client ID
        # If the token was minted for a different app, we MUST reject it.
        self.audience = audience
        
        # 3. JWKS Discovery URL (Where the IdP publishes their public keys)
        self.jwks_url = f"{self.issuer_url}/.well-known/jwks.json"
        
        # 4. PyJWT's automatic JWK Client. It fetches the public keys and caches them.
        self.jwks_client = jwt.PyJWKClient(self.jwks_url)

    def verify_id_token(self, token: str) -> dict:
        """
        Validates the OIDC ID Token cryptographically.
        This happens entirely in memory (stateless) after the JWKS is cached.
        """
        try:
            # Step 1: Look at the unverified header of the JWT to find the 'kid' (Key ID).
            # The IdP rotates their keys frequently. The 'kid' tells us WHICH public key to use.
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            
            # Step 2: Mathematically verify the signature using the downloaded public key.
            # We enforce strict checks on Issuer and Audience to prevent token substitution attacks.
            decoded_payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"], # OIDC standard requires RS256
                audience=self.audience,
                issuer=self.issuer_url,
                # leeway allows for minor clock skew between Google's servers and ours
                leeway=30 
            )
            return decoded_payload
            
        except jwt.PyJWKClientError:
            raise HTTPException(status_code=500, detail="Failed to fetch IdP Public Keys")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="ID Token has expired")
        except jwt.InvalidIssuerError:
            raise HTTPException(status_code=401, detail="Invalid Issuer. Token not from trusted IdP.")
        except jwt.InvalidAudienceError:
            raise HTTPException(status_code=401, detail="Invalid Audience. Token was not minted for this application.")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid Token: {str(e)}")


# --- 2. FASTAPI IMPLEMENTATION ---

app = FastAPI(title="Logic & Legacy: Identity Federation Node")

# Imagine this is our app's configuration for Google Login
# In production, audience comes from env: GOOGLE_CLIENT_ID
GOOGLE_ISSUER = "https://accounts.google.com"
MOCK_CLIENT_ID = "1234567890-mockclientid.apps.googleusercontent.com"

# Initialize the Federation Engine
federation_engine = OIDCFederationEngine(
    issuer_url=GOOGLE_ISSUER, 
    audience=MOCK_CLIENT_ID
)

def require_federated_identity(authorization: str = Header(..., description="Bearer <OIDC_ID_TOKEN>")) -> dict:
    """Dependency to enforce OIDC Identity checks."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    
    token = authorization.split("Bearer ")[1]
    # The engine verifies the math. If it doesn't raise an exception, the user is valid.
    return federation_engine.verify_id_token(token)

# --- 3. ROUTES ---

@app.get("/api/v1/workday/dashboard", summary="Federated Endpoint")
async def get_federated_dashboard(user_identity: dict = Depends(require_federated_identity)):
    """
    An endpoint that doesn't care about passwords or sessions.
    It only cares that Google vouched for your identity mathematically.
    """
    # The OIDC ID Token contains standard claims like 'sub' (subject ID), 'email', and 'name'
    return {
        "message": "Federation Successful",
        "identity_provider": GOOGLE_ISSUER,
        "user_email": user_identity.get("email"),
        "user_id": user_identity.get("sub"),
        "data": "Highly sensitive internal dashboard data"
    }

if __name__ == "__main__":
    import uvicorn
    # To run: python oidc_federation_engine.py
    # Note: To test this locally, you would need a REAL ID token from Google or Auth0
    # minted for the MOCK_CLIENT_ID, which is why federation is hard to mock securely!
    uvicorn.run(app, host="0.0.0.0", port=8000)
