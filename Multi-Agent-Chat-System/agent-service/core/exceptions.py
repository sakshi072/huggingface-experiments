"""Custom exceptions for the agent service."""

class ChatNotFoundError(Exception):
    """Raised when a chat session is not found."""
    pass

class ChatOwnershipError(Exception):
    """Raised when user doesn't own the chat."""
    pass

class DatabaseError(Exception):
    """Raised when a database operation fails."""
    pass

class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass

class RAGServiceError(Exception):
    """Raised when RAG service call fails."""
    pass
