"""Common API dependencies."""
from typing import Optional
import uuid

from fastapi import Header

from app.infrastructure.auth.jwt_validator import get_current_user_id

# Re-export auth dependency
__all__ = ["get_current_user_id", "get_request_ids"]


def get_request_ids(
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
) -> tuple[str, str]:
    """Get or generate request and correlation IDs."""
    request_id = x_request_id or str(uuid.uuid4())
    correlation_id = x_correlation_id or str(uuid.uuid4())
    return request_id, correlation_id
