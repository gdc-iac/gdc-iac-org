import os
import json
import logging
import urllib.request
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from models import User

logger = logging.getLogger("auth")

# Staging/Production Feature Flags
ENABLE_OIDC = os.getenv("ENABLE_OIDC", "false").lower() == "true"
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak-svc:8080/auth/realms/gdc-rag-realm")
ALGORITHMS = ["RS256"]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
jwks_cache = None

def get_jwks():
    """Fetches public verification certs from Keycloak using python stdlib (zero outside dependencies)"""
    global jwks_cache
    if jwks_cache is None and ENABLE_OIDC:
        try:
            certs_url = f"{KEYCLOAK_URL}/protocol/openid-connect/certs"
            with urllib.request.urlopen(certs_url, timeout=5) as response:
                jwks_cache = json.loads(response.read().decode())
                logger.info("OIDC: Loaded verification signature keys from Keycloak")
        except Exception as e:
            logger.error(f"OIDC: Failed to pull certificates: {e}")
    return jwks_cache

async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> User:
    if ENABLE_OIDC:
        if not token:
            # Fallback check for standard Authorization header
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing dynamic identity validation bearer token"
                )
        try:
            jwks = get_jwks()
            if not jwks:
                jwks = get_jwks() # Retry once
                if not jwks:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Identity certificates provider offline"
                    )
            
            # Verify cryptography signature (verify_aud=False aligns with default GDC OIDC client payloads)
            payload = jwt.decode(token, jwks, algorithms=ALGORITHMS, options={"verify_aud": False, "leeway": 60})
            user_id = payload.get("preferred_username") or payload.get("sub")
            
            # Extract roles and construct user model
            roles = payload.get("realm_access", {}).get("roles", [])
            user_role = "admin" if "admin" in roles else "user"
            
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid verification credentials claims"
                )
            return User(id=user_id, role=user_role)
        except JWTError as e:
            logger.error(f"OIDC Claim Check Failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Cryptographic credentials validation failed: {str(e)}"
            )
    else:
        # Standard Fallback to baseline Local Mock Authentication
        user_id = request.headers.get("X-User-ID")
        user_role = request.headers.get("X-User-Role", "user")
        if not user_id:
            user_id = "anonymous"
        return User(id=user_id, role=user_role)
