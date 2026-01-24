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
from app.core.exception_handler import register_exception_handlers
from app.core.middleware import TracingMiddleware
from app.core.exceptions import (
    RetrievalBaseException,
    ValidationException,
    AuthException,
    StorageException,
    DatabaseException,
    ServiceUnavailableException,
    DocumentNotFound,
    DocumentParsingException,
    DocumentTooLargeException,
    DuplicateDocumentException,
    InsufficientContentException,
    InvalidTokenException,
    ExpiredTokenException,
    InsufficientPermissionsException,
    InvalidParameterException,
    InvalidType
)

__all__ = [
    "verify_jwt",
    "require_scope",
    "extract_scopes",
    "has_scope",
    "validate_jwt_token",
    "feature_flags",
    "FeatureFlags",
    "settings",
    "register_exception_handlers",
    "TracingMiddleware",
    "RetrievalBaseException",
    "ValidationException",
    "AuthException",
    "StorageException",
    "DatabaseException",
    "ServiceUnavailableException",
    "DocumentNotFound",
    "DocumentParsingException",
    "DocumentTooLargeException",
    "DuplicateDocumentException",
    "InsufficientContentException",
    "InvalidTokenException",
    "ExpiredTokenException",
    "InsufficientPermissionsException",
    "InvalidParameterException",
    "InvalidType"
]
