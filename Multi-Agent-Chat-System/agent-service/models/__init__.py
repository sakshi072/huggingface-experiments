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

from .supervisor import (
    SupervisorState
)

from .job_search import (
    JobListing,
    JobSearchState,
    ExpandedQueryList
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
    # LangGraph models
    "SupervisorState",
    "JobListing",
    "JobSearchState",
    "ExpandedQueryList"
]
