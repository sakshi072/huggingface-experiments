"""
Core configuration and security
"""
from app.core.security import (
    verify_jwt,
    require_scope,
    extract_scopes,
    has_scope,
    validate_jwt_token
)
from app.core.feature_flags import feature_flags, FeatureFlags
from app.core.settings import settings
from app.core.exception_handler import general_exception_handler, http_exception_handler
from app.core.middleware import TracingMiddleware

__all__ = [
    "verify_jwt",
    "require_scope",
    "extract_scopes",
    "has_scope",
    "validate_jwt_token",
    "feature_flags",
    "FeatureFlags",
    "settings",
    "general_exception_handler",
    "http_exception_handler",
    "TracingMiddleware"
]
