from typing import Any, Dict, Optional

class RetrievalBaseException(Exception):
    """
    Base exception for all RAG system errors.
    """
    def __init__(
        self,
        message:str,
        error_code:str = "Retrieval Error",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code =error_code
        self.status_code =status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error":self.status_code,
            "message":self.message,
            "detail": self.details if self.details else None
        }
    
# ============================================================================
# Document Processing Exceptions
# ============================================================================

class DocumentException(RetrievalBaseException):
    """Base exception for document-related errors"""
    def __init__(self, message:str, error_code:str="DOCUMENT_ERROR", status_code: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_code=error_code, status_code=status_code, details=details)

class DocumentParsingException(DocumentException):
    """Raised when failed to parse uploaded document"""
    def __init__(self, filename:str, file_type:str, reason:str):
        super().__init__(
            message=f"Failed to parse document '{filename}",
            error_code="DOCUMENT_PARSING_FAILED",
            details={
                "filename":filename,
                "file_type":file_type,
                "reason": reason
            }
        )

class UnsupportedFileTypeException(DocumentException):
    """Raised when file type is not supported"""
    def __init__(self, file_type:str, supported_types:list):
        super().__init__(
            message=f"File type {file_type} is not supported",
            error_code="UNSUPPORTED_FILE_TYPE",
            details={
                "received_file_type": file_type,
                "supported_file_types": supported_types
            }
        )

class InsufficientContentException(DocumentException):
    """Raised when text is too short or empty"""
    def __init__(self, filename:str):
        super().__init__(
            message=f"Document '{filename} is empty or has no extractable text",
            error_code="INSUFFICIENT_DOCUMENT_CONTENT",
            details={
                "filename": filename
            }
        )

class DocumentTooLargeException(DocumentException):
    """Raised when document exceeds size limit"""
    def __init__(self, filename:str, file_size_mb:float, max_size_mb:float):
        super().__init__(
            message=f"Document '{filename} exceeds maximum size",
            error_code="DOCUMENT_TOO_LARGE",
            details={
                "filename": filename,
                "file_size_mb": round(file_size_mb,2),
                "max_size_mb": max_size_mb
            }
        )

class DuplicateDocumentException(DocumentException):
    """Raise when a duplicate document is uploaded"""
    def __init__(self, filename: str, existing_id: str):
        super().__init__(
            message=f"Document '{filename}' already exists",
            error_code="DUPLICATE_DOCUMENT",
            status_code=409,
            details={
                "filename": filename,
                "existing_document_id": existing_id
            }
        )

class DocumentNotFound(DocumentException):
    """Raise when a document is not found"""
    def __init__(self, document_id:str):
        super().__init__(
            message="Document not found",
            error_code= "DOCUMENT_NOT_FOUND",
            status_code= 404,
            details={
                "document_id": document_id
            }
        )

# ============================================================================
# Storage Exceptions
# ============================================================================

class StorageException(RetrievalBaseException):
    """Base exception for storage-related errors"""
    def __init__(self, message: str, error_code: str = "STORAGE_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_code=error_code, status_code=500, details=details)

class MinIOUploadException(StorageException):
    """Raised when MinIO upload fails"""
    def __init__(self, filename:str, reason:str):
        super().__init__(
            message=f"Failed to upload file to object storage",
            error_code="MINIO_UPLOAD_FAILED",
            details={
                "filename":filename,
                "reason":reason
            }
        )

class MinIODownloadException(StorageException):
    """Raised when MinIO download fails"""
    def __init__(self, object_key: str, reason: str):
        super().__init__(
            message=f"Failed to download file from object storage",
            error_code="MINIO_DOWNLOAD_FAILED",
            details={
                "object_key": object_key,
                "reason": reason
            }
        )

class MinIODeleteException(StorageException):
    """Raised when MinIO deletion fails"""
    def __init__(self, object_key: str, reason: str):
        super().__init__(
            message=f"Failed to delete file from object storage",
            error_code="MINIO_DELETE_FAILED",
            details={
                "object_key": object_key,
                "reason": reason
            }
        )

# ============================================================================
# Database Exceptions
# ============================================================================
class DatabaseException(RetrievalBaseException):
    """Base exception for storage-related errors"""
    def __init__(self, message:str, error_code:str = "DATABASE_ERROR", status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_code=error_code, status_code=status_code, details=details)

class DatabaseConnectionException(DatabaseException):
    """Raised when database connection fails"""
    def __init__(self, reason:str):
        super().__init__(
            message="Failed to connect to database",
            error_code="DATABASE_CONNECTION_FAILED",
            status_code=503,
            details={"reason": reason}
        )

# ============================================================================
# Search Exceptions
# ============================================================================
class SearchException(RetrievalBaseException):
    """Base exception for search-related errors"""
    def __init__(self, message: str, error_code:str = "SEARCH_ERROR", status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_code=error_code, status_code=status_code, details=details)

class InvalidQueryException(SearchException):
    """Raised when search query is invalid"""
    def __init__(self, query: str, reason: str):
        super().__init__(
            message="Invalid search query",
            error_code="INVALID_QUERY",
            status_code=400,
            details={
                "query": query[:100],  # Truncate for safety
                "reason": reason
            }
        )

# ============================================================================
# Authentication & Authorization Exceptions
# ============================================================================
class AuthException(RetrievalBaseException):
    """Base exception for auth-related errors"""
    def __init__(self, message: str, error_code:str = "AUTH_ERROR", status_code: int = 401, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_code=error_code, status_code=status_code, details=details)
    
class InvalidTokenException(AuthException):
    """Raise when token is invalid"""
    def __init__(self, reason:str):
        super().__init__(
            message="Invalid authentication token",
            error_code="INVALID_TOKEN",
            details={"reason":reason}
        )

class ExpiredTokenException(AuthException):
    """Raise when token is expired"""
    def __init__(self):
        super().__init__(
            message="Authentication token has expired",
            error_code="EXPIRED_TOKEN",
        )  

class InsufficientPermissionsException(AuthException):
    """Raise when token is invalid"""
    def __init__(self, required_scope:str, available_scopes:list):
        super().__init__(
            message="Insufficient permissions to perform this action",
            error_code="INSUFFICIENT_PERMISSIONS",
            status_code=403,
           details={
                "required_scope": required_scope,
                "available_scopes": available_scopes
            }
        )

# ============================================================================
# Validation Exceptions
# ============================================================================
class ValidationException(RetrievalBaseException):
    """Base exception for validation errors"""
    def __init__(self, message:str, error_code:str = "VALIDATION_ERROR", status_code: int = 422, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_code=error_code, status_code=422, details=details)
    
class InvalidParameterException(ValidationException):
    """Raised when request parameter is invalid"""
    def __init__(self, parameter: str, value: Any, reason: str):
        super().__init__(
            message=f"Invalid parameter: {parameter}",
            error_code="INVALID_PARAMETER",
            details={
                "parameter": parameter,
                "value": str(value),
                "reason": reason
            }
        )


class MissingParameterException(ValidationException):
    """Raised when required parameter is missing"""
    def __init__(self, parameter: str):
        super().__init__(
            message=f"Missing required parameter: {parameter}",
            error_code="MISSING_PARAMETER",
            details={"parameter": parameter}
        )

class InvalidType(ValidationException):
    """Raised when required parameter is missing"""
    def __init__(self, field: str, field_type:str, expected_type:str):
        super().__init__(
            message=f"Invalid type: {field_type}",
            error_code="INVALID_TYPE",
            details={"field": field,
                     "field_type": field_type,
                     "expected_type": expected_type}
        )
# ============================================================================
# Configuration Exceptions
# ============================================================================
class ConfigurationException(RetrievalBaseException):
    """Base exception for configuration errors"""
    def __init__(self, message: str, error_code:str = "CONFIGURATION_ERROR", status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_code=error_code, status_code=status_code, details=details)

class MissingConfigException(ConfigurationException):
    """Raised when a config is missing"""
    def __init__(self, config_key:str):
        super().__init__(
            message=f"Missing a required config: {config_key}",
            error_code="MISSING_CONFIG",
            details={
                "config_key": config_key
            }
        )

class InvalidConfigException(ConfigurationException):
    """Raised when configuration value is invalid"""
    def __init__(self, config_key: str, value: Any, reason: str):
        super().__init__(
            message=f"Invalid configuration: {config_key}",
            error_code="INVALID_CONFIGURATION",
            details={
                "config_key": config_key,
                "value": str(value),
                "reason": reason
            }
        )

# ============================================================================
# Rate Limiting Exceptions
# ============================================================================
class RateLimitException(RetrievalBaseException):
    """Raised when rate limit is exceeded"""
    def __init__(self, limit:int, window:str, retry_after:int):
        super().__init__(
            message=f"Rate limit excceeded: {limit} requests per {window}",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={
                "limit":limit,
                "window": window,
                "retry_after":retry_after
            }
        )

# ============================================================================
# Service Unavailable Exceptions
# ============================================================================

class ServiceUnavailableException(RetrievalBaseException):
    """Raised when service is temporarily unavailable"""
    def __init__(self, service_name: str, reason: str):
        super().__init__(
            message=f"Service temporarily unavailable: {service_name}",
            error_code="SERVICE_UNAVAILABLE",
            status_code=503,
            details={
                "service_name": service_name,
                "reason": reason
            }
        )