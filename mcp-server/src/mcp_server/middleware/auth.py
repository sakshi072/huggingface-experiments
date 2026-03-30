from mcp_server.models.auth0_m2m_models import TokenResponse
from typing import Optional
import asyncio
import logging
import time 
import httpx
from mcp_server.core.settings import settings
import fastmcp

logger = logging.getLogger(__name__)
class Auth0TokenManager:
    """
    Manages Oauth 2.0 access tokens with automatic refresh
    """

    def __init__(self):
        """
        Initialize token manager and cache
        """

        self._access_token: Optional[str] = None
        self._expires_at: Optional[float] = None
        self._token_scope: Optional[str] = None

        self._lock = asyncio.Lock()

        logger.info("✅ Auth0 Token Manager initialized")
    
    @property
    def is_valid_token(self) -> bool:
        """Check if cached access token is valid"""
        if not self._access_token or not self._expires_at:
            return False

        return time.time() < (self._expires_at - 60)
    
    @property
    def time_until_expiry(self) -> Optional[float]:
        if not self._expires_at:
            return None
        return max(0, self._expires_at - time.time())
    
    async def get_access_token(self, force_refresh:bool=False) -> str:
        """
        Get valid access token (from cache or Auth0)

        Args:
            force_refresh: Force fetch new token even if cached
            
        Returns:
            Valid access token
            
        Raises:
            RuntimeError: If unable to get token from Auth0
        """
        # Return from cache
        if not force_refresh and self.is_valid_token:
            logger.debug(f"✅ Using cached token (expires in {self.time_until_expiry:.0f}s)")
            return self._access_token
        
        # Fetch new token with lock
        async with self._lock:
            if not force_refresh and self.is_valid_token:
                return self._access_token

            return await self._fetch_new_token()
    
    async def _fetch_new_token(self, retry_count:int = 3) -> str:
        """
        Fetch new access token from 
        """
        logger.info("Fetching new access token from Auth0")

        for attempt in range(retry_count):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        settings.auth0_token_url,
                        json = {
                            "client_id": settings.AUTH0_CLIENT_ID,
                            "client_secret": settings.AUTH0_CLIENT_SECRET,
                            "audience": settings.AUTH0_AUDIENCE,
                            "grant_type": "client_credentials"
                        }
                    )
                    response.raise_for_status()
                    data = response.json()

                    token_response = TokenResponse(**data)

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
                    f" Auth0 token request failed (attempt {attempt-1}/{retry_count}):"
                    f"Status {e.response.status_code}"
                )

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

                if attempt < retry_count -1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            except Exception as e:
                last_error = e
                logger.error(f"❌ Unexpected error fetching token: {e}")

                if attempt < retry_count - 1:
                    await asyncio.sleep(2**attempt)
            
        raise RuntimeError(
            f"Failed to fetch access token after {retry_count} attempts: {last_error}"
        )
    
    async def revoke_token(self) -> None:
        """Revoke current token (forces refresh on next request)"""
        async with self._lock:
            self._access_token = None
            self._expires_at = None
            self._token_scope = None

    
_token_manager: Optional[Auth0TokenManager] = None

def get_token_manager() -> Auth0TokenManager:
    """Get global token manager instance"""
    global _token_manager

    if _token_manager is None:
        _token_manager = Auth0TokenManager()

    return _token_manager

async def get_token() -> str:
    """Get current access token"""
    manager = get_token_manager()
    return await manager.get_access_token()