from pydantic import BaseModel, Field
from typing import Optional
class SearchKnowledgeBaseArgs(BaseModel):
    query: str = Field(..., description="Query to search in the knowledge base")
    top_k: Optional[int] = Field(default=3, gt=0, description="Number of search results to return")