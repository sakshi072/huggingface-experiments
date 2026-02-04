"""Models package - re-exports all models for backward compatibility."""

from .domain import (
    HistoryMessage,
    ChatSessionMetadata,
    CursorInfo,
)

from .database import (
    PyObjectId,
    MessageDocument,
    ChatMetadataDocument,
)

from .api import (
    ChatPrompt,
    InferenceResponse,
    HistoryResponse,
    CreateChatRequest,
    CreateChatResponse,
    ChatSessionsResponse,
    UpdateTitleRequest,
    GenerateTitleRequest,
    GenerateTitleResponse,
    PaginationParams,
    HealthCheckResponse,
)

from .mcp import MCPClientConfig

__all__ = [
    # Domain models
    "HistoryMessage",
    "ChatSessionMetadata",
    "CursorInfo",
    # Database models
    "PyObjectId",
    "MessageDocument",
    "ChatMetadataDocument",
    # API models
    "ChatPrompt",
    "InferenceResponse",
    "HistoryResponse",
    "CreateChatRequest",
    "CreateChatResponse",
    "ChatSessionsResponse",
    "UpdateTitleRequest",
    "GenerateTitleRequest",
    "GenerateTitleResponse",
    "PaginationParams",
    "HealthCheckResponse",
    #MCP Client
    "MCPClientConfig"
]
