"""
Auth0 JWT Token Validator

Validates JWT tokens from Auth0 for Client Credentials flow.
"""
import os
import logging
from typing import Optional, Dict, List
from functools import lru_cache

import httpx
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWSSignatureError, JWTClaimsError
from fastapi import Header, HTTPException, status, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

security = HTTPBearer()

# ============================================================================
# Configuration
# ============================================================================

class Auth0Config:
    """Auth0 configuration for JWT validation"""

    def __init__(self):
        self.domain = os.getenv("AUTH0_DOMAIN", "")
        self.audience = os.getenv("AUTH0_AUDIENCE", "")
        self.issuer = f"https://{self.domain}/" if self.domain else ""
        self.algorithms = ["RS256"]  # Auth0 uses RS256 for M2M
        
        if not self.domain or not self.audience:
            raise ValueError(
                "AUTH0_DOMAIN and AUTH0_AUDIENCE must be set for JWT validation"
            )
    
    @property
    def jwks_url(self) -> str:
        """Get JWKS (JSON Web Key Set) URL"""
        return f"https://{self.domain}/.well-known/jwks.json"
    

# Global Config
_config: Optional[Auth0Config] = None

def get_auth0_config() -> Auth0Config:
    """Get Auth0 configuration (singleton)"""
    global _config
    if _config is None:
        _config = Auth0Config()
    return _config

# ============================================================================
# JWKS Fetcher (with caching)
# ============================================================================

@lru_cache(maxsize=1)
def get_jwks() -> dict:
    """
    Fetch JWKS (JSON Web Key Set) from Auth0
    
    JWKS contains public keys used to verify JWT signatures.
    Cached to avoid fetching on every request.
    
    Returns:
        JWKS dictionary
    """
    config = get_auth0_config()

    try:
        response = httpx.get(config.jwks_url, timeout=10.0)
        response.raise_for_status()
        jwks = response.json()
        logger.debug(f"✅ Fetched JWKS with {len(jwks.get('keys', []))} keys")
        return jwks
    except Exception as e:
        logger.error(f"❌ Failed to fetch JWKS: {e}")
        raise RuntimeError(f"Unable to fetch JWKS from Auth0: {e}")

def get_signing_key(token:str) -> dict:
    """
    Get signing key from JWKS for given token
    
    Process:
    1. Decode token header (without verification)
    2. Extract 'kid' (key ID)
    3. Find matching key in JWKS
    4. Return public key
    
    Args:
        token: JWT token
        
    Returns:
        Signing key dictionary
    """
    try:
        # Decode header without verification
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')

        if not kid:
            raise ValueError("Token header missing 'kid' (key ID)")
        
        # Get JWKS
        jwks = get_jwks()

        # Find matching key
        for key in jwks.get("keys", []):
            if key.get('kid') == kid:
                return key
        
        raise ValueError(f"Unable to find singing key with kid: {kid}")

    except Exception as e:
        logger.error(f"❌ Error getting signing key: {e}")
        raise

# ============================================================================
# Token Validation
# ============================================================================

def validate_jwt_token(token:str) -> dict:
    """
    Validate JWT token from Auth0
    
    Validation Steps (in order):
    1. Get signing key from JWKS
    2. Verify signature using public key
    3. Verify expiration (exp claim)
    4. Verify audience (aud claim)
    5. Verify issuer (iss claim)
    6. Return decoded payload
    
    Args:
        token: JWT access token
        
    Returns:
        Decoded token payload (claims)
        
    Raises:
        ValueError: If token is invalid
    """
        
    config = get_auth0_config()

    try:
        # Get singing key
        signing_key = get_signing_key(token)

        # Validate and decode token
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=config.algorithms,
            audience=config.audience,
            issuer=config.issuer
        )

        logger.debug(f"✅ Token validated for subject: {payload.get('sub')}")
        return payload
    except ExpiredSignatureError:
        logger.warning("❌ Token validation failed: Token has expired")
        raise ValueError("Token has expired")
    except JWTClaimsError as e:
        logger.warning(f"❌ Token validation failed: Invalid claims - {e}")
        raise ValueError(f"Invalid token claims: {e}")
    except JWTError as e:
        logger.warning(f"❌ Token validation failed: {e}")
        raise ValueError(f"Invalid token: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error validating token: {e}")
        raise ValueError(f"Token validation error: {e}")

def extract_scopes(token_payload:dict) -> List[str]:
    """
    Extract scopes from token payload
    
    Args:
        token_payload: Decoded JWT payload
        
    Returns:
        List of scopes (permissions)
    """
    scope_string = token_payload.get("scope","")
    return scope_string.split() if scope_string else []

def has_scope(required_scope:str, token_payload:dict) -> bool:
    """
    Check if token has required scope
    
    Args:
        required_scope: Scope to check for
        token_payload: Decoded JWT payload
        
    Returns:
        True if token has the scope
    """
    scopes = extract_scopes(token_payload)
    return required_scope in scopes

# ============================================================================
# FastAPI Dependencies
# ============================================================================

def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    FastAPI dependency to verify JWT token
    
    Usage:
        @app.post("/search")
        async def search(
            request: SearchRequest,
            token: dict = Depends(verify_jwt)
        ):
            # token contains validated payload
            return {"results": [...]}
    
    Args:
        credentials: HTTP Authorization credentials from header
        
    Returns:
        Decoded token payload
        
    Raises:
        HTTPException: 401 if token invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authentication": "Bearer"}
        )
    
    token = credentials.credentials

    try:
        payload = validate_jwt_token(token)
        return payload
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"}
        )



def require_scope(required_scope:str):
    """
    FastAPI dependency factory for scope-based authorization
    
    Usage:
        @app.delete("/documents/{id}")
        async def delete_doc(
            id: str,
            token: dict = Depends(require_scope("delete:documents"))
        ):
            # Only called if token has delete:documents scope
            return {"deleted": id}
    
    Args:
        required_scope: Scope that must be present in token
        
    Returns:
        Dependency function
    """
    def scope_checker(token:dict = Security(verify_jwt)) -> dict:
        """Check if token has required scope"""
        if not has_scope(required_scope, token):
            scopes = extract_scopes(token)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "INSUFFICIENT_PERMISSIONS",
                    "message": f"Required scope '{required_scope}' not found",
                    "available_scopes": scopes
                }
            )
        return token
    
    return scope_checker