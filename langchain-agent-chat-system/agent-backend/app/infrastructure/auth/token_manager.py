"""
Auth0 Token Manager for Client Credentials Grant

Handles:
- Token acquisition from Auth0
- Token caching and refresh
- Automatic retry on expiration
- Thread-safe token management
"""
import os
import time
import logging
import asyncio
from typing import Optional
from app.core.settings import settings
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration Models
# ============================================================================

# class Auth0Config(BaseModel):
#     """Auth0 configuration for Client Credentials flow"""

#     domain: str = Field(..., description="Auth0 tenant domain")
#     client_id: str = Field(..., description="M2M application client ID")
#     client_secret: str = Field(..., description="M2M application client secret")
#     audience: str = Field(..., description="API identifier")
#     token_url: Optional[str] = Field(None, description="Token endpoint URL")

#     def __init__(self, **data):
#         """Initialize with data or from environment"""
#         # If no data provided, load from environment
#         if not data:
#             data = {
#                 "domain": os.getenv("AUTH0_DOMAIN", ""),
#                 "client_id": os.getenv("CLIENT_ID", ""),
#                 "client_secret": os.getenv("CLIENT_SECRET", ""),
#                 "audience": os.getenv("AUDIENCE", ""),  # M2M audience!
#             }
        
#         # Call parent __init__
#         super().__init__(**data)
        
#         # Auto-construct token URL if not provided
#         if not self.token_url:
#             self.token_url = f"https://{self.domain}/oauth/token"
    
#     @classmethod
#     def from_env(cls) -> "Auth0Config":
#         """Load configuration from environment variables"""
#         return cls(
#             domain=os.getenv("AUTH0_DOMAIN", ""),
#             client_id=os.getenv("CLIENT_ID", ""),
#             client_secret=os.getenv("CLIENT_SECRET", ""),
#             audience=os.getenv("AUDIENCE", ""),  # M2M audience
#         )
    
#     def validate_config(self) -> tuple[bool, str]:
#         """
#         Validate configuration is complete
        
#         Returns:
#             (is_valid, error_message)
#         """
#         if not self.domain:
#             return False, "AUTH0_DOMAIN is required"
#         if not self.client_id:
#             return False, "AUTH0_CLIENT_ID is required"
#         if not self.client_secret:
#             return False, "AUTH0_CLIENT_SECRET is required"
#         if not self.audience:
#             return False, "AUTH0_M2M_AUDIENCE is required"
#         return True, ""


class TokenResponse(BaseModel):
    """Auth0 token response"""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int  # In seconds
    scope: Optional[str] = None


# ============================================================================
# Token Manager
# ============================================================================

class Auth0TokenManager:
    """
    Manages OAuth 2.0 access tokens with automatic refresh
    
    Features:
    - Token caching (reduces Auth0 API calls)
    - Automatic refresh before expiration
    - Thread-safe with asyncio locks
    - Retry logic for transient failures
    """

    def __init__(self, service:str):
        """
        Initialize token manager
        
        Args:
            config: Auth0 configuration
        """
        
        # Token cache
        self._access_token: Optional[str] = None
        self._expires_at: Optional[float] = None
        self._token_scope: Optional[str] = None
        self.service:str = service

        # Thread safety
        self._lock = asyncio.Lock()

        # Validate configuration
        # is_valid, error = config.validate_config()
        # if not is_valid:
        #     raise ValueError(f"Invalid Auth0 configuration: {error}")
        
        logger.info("✅ Auth0 Token Manager initialized")
        logger.info(f"   Domain: {getattr(settings, f'{service}_DOMAIN', None)}")
        logger.info(f"   Client ID: {getattr(settings, f'{service}_CLIENT_ID', None)}...")
        logger.info(f"   Audience: {getattr(settings, f'{service}_AUDIENCE', None)}")
    
    @property
    def is_token_valid(self) -> bool:
        """
        Check if cached token is still valid
        
        Returns:
            True if token exists and not expired
        """
        if not self._access_token or not self._expires_at:
            return False
        
        # Add 60-second buffer to prevent using almost-expired tokens
        return time.time() < (self._expires_at - 60)

    @property
    def time_until_expiry(self) -> Optional[float]:
        """
        Get seconds until token expires
        
        Returns:
            Seconds until expiry, or None if no token
        """
        if not self._expires_at:
            return None
        return max(0, self._expires_at - time.time())
    
    async def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Get valid access token (from cache or Auth0)
        
        This is the main method clients use. It handles:
        1. Returning cached token if still valid
        2. Fetching new token if needed
        3. Thread-safe token refresh
        
        Args:
            force_refresh: Force fetch new token even if cached
            
        Returns:
            Valid access token
            
        Raises:
            RuntimeError: If unable to get token from Auth0
        """
        # Fast path: Return cached token if valid
        if not force_refresh and self.is_token_valid:
            logger.debug(f"✅ Using cached token (expires in {self.time_until_expiry:.0f}s)")
            return self._access_token
        
        # Slow path: Fetch new token with lock
        async with self._lock:
            # Double-check: Another thread might have refreshed while we waited
            if not force_refresh and self.is_token_valid:
                logger.debug("Token refreshed by another request")
                return self._access_token
            
            # Fetch new token
            return await self._fetch_new_token()
        
    async def _fetch_new_token(self, retry_count: int = 3) -> str:
        """
        Fetch new access token from Auth0
        
        Args:
            retry_count: Number of retries on failure
            
        Returns:
            New access token
            
        Raises:
            RuntimeError: If all retries fail
        """
        logger.info("🔄 Fetching new access token from Auth0...")

        # request_payload = {
        #     "client_id": self.config.client_id,
        #     "client_secret": self.config.client_secret,
        #     "audience": self.config.audience,
        #     "grant_type": "client_credentials"
        # }
        logger.info("✅ Auth0 Token Manager initialized")
        logger.info(f"   Client ID: {getattr(settings, f'{self.service}_CLIENT_ID', None)}")
        logger.info(f"   Client Secret: {getattr(settings, f'{self.service}_CLIENT_SECRET')}")
        logger.info(f"   Audience: {getattr(settings, f'{self.service}_AUDIENCE', None)}")
        logger.info(f"   Token URL: {getattr(settings, f'{self.service.lower()}_token_url', None)}")
        request_payload = {
            "client_id": getattr(settings, f'{self.service}_CLIENT_ID', None),
            "client_secret": getattr(settings, f'{self.service}_CLIENT_SECRET', None),
            "audience": getattr(settings, f'{self.service}_AUDIENCE', None),
            "grant_type": "client_credentials"
        }

        last_error = None

        for attempt in range(retry_count):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        getattr(settings, f'{self.service.lower()}_token_url', None),
                        json=request_payload,
                        headers={"Content-Type": "application/json"}
                    )

                    response.raise_for_status()
                    data = response.json()

                    # Parse response
                    token_response = TokenResponse(**data)

                    # Cache token
                    self._access_token = token_response.access_token
                    self._expires_at = time.time() + token_response.expires_in
                    self._token_scope = token_response.scope

                    logger.info(
                        f"✅ New access token acquired "
                        f"(expires in {token_response.expires_in}s, "
                        f"scope: {token_response.scope})"
                    )

                    return self._access_token
                    
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(
                    f"❌ Auth0 token request failed (attempt {attempt + 1}/{retry_count}): "
                    f"Status {e.response.status_code}"
                )
                
                # Log response body for debugging
                try:
                    error_body = e.response.json()
                    logger.error(f"   Error details: {error_body}")
                except:
                    logger.error(f"   Error text: {e.response.text}")

                # Don't retry on 4xx errors (client errors)
                if 400 <= e.response.status_code < 500:
                    raise RuntimeError(
                        f"Auth0 authentication failed: {e.response.text}"
                    )
                
                # Exponential backoff for 5xx errors
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = e
                logger.error(f"❌ Unexpected error fetching token: {e}")
                
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)
        
        # All retries failed
        raise RuntimeError(
            f"Failed to fetch access token after {retry_count} attempts: {last_error}"
        )
    
    async def revoke_token(self) -> None:
        """
        Revoke current token (forces refresh on next request)
        
        Useful for:
        - Testing token refresh
        - Security incident response
        - Immediate permission changes
        """
        async with self._lock:
            logger.info("🔄 Revoking cached token")
            self._access_token = None
            self._expires_at = None
            self._token_scope = None
    
    def get_metrics(self) -> dict:
        """
        Get token manager metrics (for monitoring)
        
        Returns:
            Dictionary with metrics
        """
        return {
            "token_valid": self.is_token_valid,
            "time_until_expiry": self.time_until_expiry,
            "current_scope": self._token_scope
        }


# ============================================================================
# Global Instance
# ============================================================================

_token_manager: Optional[Auth0TokenManager] = None


def get_token_manager(service:str) -> Auth0TokenManager:
    """
    Get global token manager instance (singleton pattern)
    
    Returns:
        Token manager instance
    """
    global _token_manager

    if _token_manager is None:
        # config = Auth0Config.from_env()
        _token_manager = Auth0TokenManager(service)
    
    return _token_manager


# ============================================================================
# Convenience Functions
# ============================================================================

async def get_access_token(service:str) -> str:
    """
    Get current access token (convenience function)
    
    Returns:
        Valid access token
    """
    manager = get_token_manager(service)
    return await manager.get_access_token()


def get_token_metrics() -> dict:
    """Get token manager metrics (convenience function)"""
    try:
        manager = get_token_manager()
        return manager.get_metrics()
    except Exception as e:
        return {"error": str(e)}