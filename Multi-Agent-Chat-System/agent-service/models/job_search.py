from typing import TypedDict, List, Dict, Optional, Annotated
from operator import add
from pydantic import BaseModel, Field

class JobListing(BaseModel):
    """Structured Job Listing"""
    title:str = Field(..., min_length=2, description="Job title")
    company: str = Field(..., description="Company for which role is open")
    location:str = Field(..., description="Work location")
    url: str = Field(..., description="Job posting URL")
    description: str = Field(..., description="Job description")
    requirements: List[str] = Field(..., description="Job requirements")
    salary: Optional[str] = Field(None, description="Annual salary in USD")
    job_type: Optional[str] = Field(None, description="Remote, Hybrid, or Onsite")
    relevance_score: float = Field(default=0.0, description="Similarity to query")

    class Config:
        # Make it JSON-serializable for FastAPI
        json_schema_extra = {
            "example": {
                "title": "Senior AI Engineer",
                "company": "Apple",
                "location": "San Francisco",
                "url": "apple.com/careers",
                "description": "As an AI engineer you will be responsible for ...",
                "requirements": "Skills required as Python, FastAPI",
                "salary": "$200k",
                "job_type":"Hybrid",
                "relevance_score": 0.9
            }
        }

class ExpandedQueryList(BaseModel):
    expanded_queries: List[str] = Field(..., description="List of expanded queries")

class JobSearchState(TypedDict):
    """State for job search workflow."""
    # Input
    user_query:str
    max_results:int
    time_window_hours:int

    # Query expansion
    expanded_queries: List[str]

    # Search results
    raw_search_results: Annotated[List[Dict], add]

    # Reranked jobs
    ranked_raw_results: List[Dict]

    # Parsed Jobs
    jobs: List[JobListing]

    # Errors
    errors: Annotated[List[str], add]

    # Final output
    final_results: Optional[List[dict]]
