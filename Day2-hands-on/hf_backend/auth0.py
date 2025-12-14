"""
JWT Token Validation Middleware for FastAPI
Validates Auth0 JWT tokens using RS256 algorithm

Security Features:
1. Verifies JWT signature using Auth0's public key (JWKS)
2. Validates token expiration (exp claim)
3. Validates issuer (iss claim)
4. Validates audience (aud claim)
5. Extracts user_id from subject (sub claim)
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import httpx
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic_settings import BaseSettings

logger = logging.getLogger("Auth")

class Auth0Config(BaseSettings):
    """Auth0 configuration from environment variables"""
    
    AUTH0_DOMAIN: str
    AUTH0_AUDIENCE: str
    AUTH0_ALGORITHMS: str = "RS256"

    class Config: 
        env_file = ".env"
        case_sensitive = True
        extra = "allow"

    @property
    def issuer(self) -> str:
        """Construct issuer URL from domain"""
        return f"https://{self.AUTH0_DOMAIN}/"
    @property
    def jwks_url(self) -> str:
        return f"https://{self.AUTH0_DOMAIN}/.well-known/jwks.json"
    @property
    def alogirthm_list(self) -> list[str]:
        return [alg.strip() for alg in self.AUTH0_ALGORITHMS.split(",")]
    

try:
    auth0_config = Auth0Config()
    logger.info(f"Auth0 configured: domain={auth0_config.AUTH0_DOMAIN}, audience={auth0_config.AUTH0_AUDIENCE}")
except Exception as e:
    logger.error(f"Failed to load Auth0 configuration: {e}")
    raise

# --- JWKS Cache ---

class JWKSCache:
    """
    Caches Auth0's public keys (JWKS) to avoid fetching on every request
    Keys are used to verify JWT signatures
    """

    def __init__(self):
        self._jwks: Optional[Dict[str,Any]] = None
        self._last_fetch: Optional[datetime] = None
        self._cache_duration_seconds = 3600

    async def get_jwks(self) -> Dict[str, Any]:
        """
        Get JWKS from cache or fetch from Auth0
        
        JWKS contains public keys in JWK format:
        {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "key-id",
                    "use": "sig",
                    "n": "modulus",
                    "e": "exponent"
                }
            ]
        }
        """
        now = datetime.now(timezone.utc)

        if self._jwks and self._last_fetch:
            age = (now - self._last_fetch).total_seconds()
            if age < self._cache_duration_seconds:
                logger.debug("Using cache jwks")
                return self._jwks

        try:
            logger.info("Fetching JWKS from Auht...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    auth0_config.jwks_url,
                    timeout=10.0
                )
                response.raise_for_status()

                self._jwks = response.json()
                self._last_fetch = now

                logger.info(f"JWKS fetched successfully ({len(self._jwks.get('keys', []))} keys)")
                return self._jwks
        except httpx.HTTPError as e:
            logger.info(f"Failed to fetch JWKS: {e}")

            if self._jwks:
                logger.warning("Using stale JWKS cache due to fetch failure")
                return self._jwks
            
            raise HTTPException(
                status_code=500,
                detail="Unable to fetch authentication keys"
            )
        
jwks_cache = JWKSCache()

security = HTTPBearer()

async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """
    Verify JWT token from Authorization header
    
    Steps:
    1. Extract token from "Bearer <token>" header
    2. Decode header to get key ID (kid)
    3. Fetch matching public key from JWKS
    4. Verify signature using public key
    5. Validate claims (exp, iss, aud)
    6. Return decoded payload
    
    Args:
        credentials: HTTP Bearer token credentials
    
    Returns:
        Dict containing token payload (claims)
    
    Raises:
        HTTPException: If token is invalid
    """

    token = credentials.credentials

    try: 
        # Step 1: Decode token header (without verification) to get key ID
        unverified_header = jwt.get_unverified_header(token)

        # Step 2: Get key ID from token header
        kid = unverified_header["kid"]
        if not kid:
            logger.error("Token missing 'kid' in header")
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing key ID"
            )

        # Step 3: Get JWKS (public keys) from Auth0
        jwks = await jwks_cache.get_jwks()

        # Step 4: Find matching public key
        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break
        
        if not rsa_key:
            logger.error(f"No matching key found for kid: {kid}")
            raise HTTPException(
                status_code=401,
                detail="Invalid token: unable to find matching key"
            )
        
        # Step 5: Verify signature and decode token
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=auth0_config.alogirthm_list,
            audience=auth0_config.AUTH0_AUDIENCE,
            issuer=auth0_config.issuer,
        )

        logger.debug(f"Token verified for user: {payload.get('sub', 'unknown')[:8]}...")
        return payload
    except ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except JWTClaimsError as e:
        logger.error(f"Invalid token claims: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token claims: {str(e)}"
        )
    except JWTError as e:
        logger.error(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials"
        )
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal authentication error"
        )

# --- User Context Dependency ---

async def get_current_user_id(
    token_payload: Dict[str, Any] = Depends(verify_token)
) -> str:
    """
    Extract user ID from validated token
    
    The 'sub' (subject) claim contains the unique user identifier
    Format: "auth0|<user-id>" or "google-oauth2|<user-id>" etc.
    
    Args:
        token_payload: Validated JWT payload
    
    Returns:
        User ID (sub claim from token)
    
    Raises:
        HTTPException: If sub claim is missing
    """

    user_id = token_payload.get("sub")

    if not user_id:
        logger.error("Token payload missing 'sub' claim" )
        raise HTTPException(
            status_code=401,
            detail="Invalid token: missing user identifier"
        )
    return user_id

async def get_token_payload(
    token_payload: Dict[str, Any] = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Get full token payload (all claims)
    
    Useful for accessing additional claims like:
    - email
    - name
    - permissions
    - custom claims
    """
    return token_payload
