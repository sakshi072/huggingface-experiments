from pydantic import BaseModel, Field

class SearchKnowledgeBaseArgs(BaseModel):
    query: str = Field(..., description="The search query")
    top_k: int = Field(default=3, gt=0, description="Number of results")