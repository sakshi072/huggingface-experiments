"""
Core configuration and security
"""
from app.core.security import (
    verify_jwt,
    require_scope,
    extract_scopes,
    has_scope,
    validate_jwt_token,
    Auth0Config,
    get_auth0_config,
)
from app.core.feature_flags import feature_flags, FeatureFlags

__all__ = [
    "verify_jwt",
    "require_scope",
    "extract_scopes",
    "has_scope",
    "validate_jwt_token",
    "Auth0Config",
    "get_auth0_config",
    "feature_flags",
    "FeatureFlags",
]
