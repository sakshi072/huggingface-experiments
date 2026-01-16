"""
Job Search Tool - Real-time job discovery with semantic matching

Features:
1. Web search integration for real-time job listings
2. Semantic similarity matching between user query and job results
3. Reranking based on relevance scores
4. Structured job data extraction
"""

import logging
import json
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from langchain.tools import BaseTool
from sentence_transformers import SentenceTransformer
from numpy import dot
from numpy.linalg import norm

logger = logging.getLogger(__name__)

class JobSearchInput(BaseModel):
    """Input schema for job search tool"""

    query: str = Field(
        description="Job search query with role, location, skills, etc. "
        "Example: 'senior backend engineer Python remote' or 'ML engineer NYC'"
    )
    time_window_hours: int = Field(
        default=48,
        description="How recent the jobs should be (in hours). Default: 48 hours"
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of jobs to return after reranking"
    )

class JobListing(BaseModel):
    """Structured job listing data"""

    title: str
    company: str
    location: str
    url: str
    snippet: str
    posted_date: Optional[str] = None
    salary: Optional[str] = None
    job_type: Optional[str] = None
    relevance_score: Optional[float] = None

_EMBEDDER_CACHE = None

class JobSearchTool(BaseTool):
    """
    Real-time job search tool with semantic matching
    
    Process:
    1. Execute web search for job listings
    2. Parse and structure results
    3. Generate embeddings for query and results
    4. Compute semantic similarity scores
    5. Rerank results by relevance
    6. Return top N jobs
    """

    name: str = "search_jobs"
    description: str = """Search for job listings in real-time based on role, skills, and preferences.
    
    Use this when the user wants to:
    - Find job openings
    - Search for specific roles or positions
    - Look for jobs with certain skills or technologies
    - Filter by location, remote work, or time posted
    
    The tool returns recent job listings ranked by relevance to the search query.
    
    Input should include:
    - Role/position (e.g., "backend engineer", "data scientist")
    - Skills/technologies (e.g., "Python", "React", "AWS")
    - Location preferences (e.g., "NYC", "remote", "San Francisco")
    - Other preferences (e.g., "startup", "senior level")
    """

    args_schema: type[BaseModel] = JobSearchInput

    # Dependencies
    embedder: Any = None
    web_search_function: Any = None

    def __init__(self, web_search_function, **kwargs):
        """
        Initialize job search tool
        
        Args:
            web_search_function: Function to call web search API
                Should accept (query: str) and return search results
        """
        super().__init__(**kwargs)

        global _EMBEDDER_CACHE
        # Initialize embedder for semantic matching
        logger.info("🔧 Loading embedding model for job matching...")
        # Only load once across all instances
        if _EMBEDDER_CACHE is None:
            logger.info("🔧 Loading embedding model (first time)...")
            _EMBEDDER_CACHE = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        else:
            logger.info("✅ Reusing cached embedding model")

        self.embedder = _EMBEDDER_CACHE
        # Store web search function
        self.web_search_function = web_search_function

        logger.info("✅ Job search tool initialized")
    
    def _run(self, query: str, time_window_hours: int = 168, max_results: int = 5) -> str:
        """Sync implementation - not used in async context"""
        raise NotImplementedError("Use _arun for async execution")
    
    async def _arun(self, query: str, time_window_hours: int = 168, max_results: int = 5) -> str:
        """
        Execute job search with semantic matching
        
        Args:
            query: Job search query
            time_window_hours: Recency filter (hours)
            max_results: Max jobs to return
            
        Returns:
            Formatted job listings with relevance scores
        """
        try:
            logger.info(f"🔍 Job search: '{query}' (last {time_window_hours}h)")

            # Step 1: Build search query with time constraint
            search_query = self._build_search_query(query, time_window_hours)

            # Step 2: Execute web search
            search_results = await self.web_search_function(search_query)

            if not search_results or len(search_results) == 0:
                return "No job listings found matching your criteria. Try broadening your search terms or increasing the time window."

            logger.info(f"📊 Found {len(search_results)} raw results")

            # Step 3: Parse and structure job listings
            job_listings = self._parse_search_results(search_results)

            if not job_listings:
                return "Found results but couldn't extract structured job data. Try refining your query."

            # Step 4: Semantic matching and reranking
            ranked_jobs = self._rank_by_semantic_similarity(query, job_listings)

            # Step 5: Return top N results
            top_jobs = ranked_jobs[:max_results]

            logger.info(f"✅ Returning {len(top_jobs)} ranked jobs")

            return self._format_results(top_jobs, query)

        except Exception as e:
            logger.error(f"❌ Job search error: {e}")
            return f"Error searching for jobs: {str(e)}"
    
    def _build_search_query(self, user_query: str, time_window_hours: int) -> str:
        """
        Build optimized search query for job boards
        
        Strategy:
        - Add job-specific keywords
        - Include time constraint
        - Prioritize major job boards
        """
        # Build time constraint
        if time_window_hours <= 24:
            time_filter = "posted today"
        elif time_window_hours <= 72:
            time_filter = f"posted within {time_window_hours // 24} days"
        else:
            time_filter = "recent jobs"

        # Combine query components
        # Format: "<user query> jobs <time filter> site:linkedin.com OR site:indeed.com"
        enhanced_query = f"{user_query} jobs {time_filter} careers hiring"
        return enhanced_query
    
    def _parse_search_results(self, search_results: List[Dict]) -> List[JobListing]:
        """
        Parse raw search results into structured job listings
        
        Args:
            search_results: Raw web search results
            
        Returns:
            List of structured JobListing objects
        """
        jobs = []

        for result in search_results:
            try:
                # Extract fields from search result
                # Expected format: {title, url, snippet, ...}
                job = JobListing(
                    title=self._extract_job_title(result),
                    company=self._extract_company(result),
                    location=self._extract_location(result),
                    url=result.get('url', result.get('link', '')),
                    snippet=result.get('snippet', result.get('description', '')),
                    posted_date=self._extract_posted_date(result),
                    salary=self._extract_salary(result),
                    job_type=self._extract_job_type(result)
                )

                jobs.append(job)
            except Exception as e:
                logger.warning(f"Failed to parse job result: {e}")
                continue

        return jobs
    
    def _extract_job_title(self, result: Dict) -> str:
        """Extract job title from search result"""
        title = (
            result.get('title') or
            result.get('name') or
            result.get('snippet', '')[:100]
        )
        return title.strip()
    
    def _extract_company(self, result: Dict) -> str:
        """Extract company name from search result"""
        snippet = result.get('snippet', '')
        url = result.get('url', '')

        # Common patterns: "at Company Name" or "Company Name is hiring"
        if 'at' in snippet:
            parts = snippet.split('at ')
            if len(parts) > 1:
                company = parts[1].split(' is ')[0].split(' -')[0].strip()
                return company[:50]  # Limit length
        
        # Extract from URL domain
        if 'linkedin.com/company/' in url:
            company = url.split('linkedin.com/company/')[1].split('/')[0]
            return company.replace('-', ' ').title()
        
        return "Unknown Company"
    
    def _extract_location(self, result: Dict) -> str:
        """Extract location from search result"""
        snippet = result.get('snippet', '').lower()

        # Common location indicators
        location_patterns = ['remote', 'hybrid', 'onsite', 'nyc', 'san francisco', 
                           'sf', 'los angeles', 'boston', 'seattle', 'austin', 'fremont', 'palo alto']
        
        for pattern in location_patterns:
            if pattern in snippet:
                return pattern.title()
        
        return "Location not specified"
    
    def _extract_posted_date(self, result: Dict) -> Optional[str]:
        """Extract posting date from result"""
        return None
    
    def _extract_salary(self, result: Dict) -> Optional[str]:
        """Extract salary information from snippet"""
        snippet = result.get('snippet', '')

        # Look for salary patterns: $XXk, $XX-XXk, etc.
        import re
        salary_pattern = r'\$[\d,]+(k|K)?(-\$[\d,]+(k|K)?)?'
        match = re.search(salary_pattern, snippet)
        
        if match:
            return match.group(0)
        
        return None

    def _extract_job_type(self, result: Dict) -> Optional[str]:
        """Extract job type (remote/hybrid/onsite)"""
        snippet = result.get('snippet', '').lower()

        if 'remote' in snippet:
            return 'remote'
        elif 'hybrid' in snippet:
            return 'hybrid'
        elif 'on-site' in snippet or 'onsite' in snippet:
            return 'onsite'
        
        return None
    
    def _rank_by_semantic_similarity(
        self,
        query: str,
        jobs: List[JobListing]
    ) -> List[JobListing]:
        """
        Rank jobs by semantic similarity to query
        
        Process:
        1. Generate query embedding
        2. Generate job text embeddings (title + snippet)
        3. Compute cosine similarity scores
        4. Sort by score (descending)
        
        Args:
            query: User's search query
            jobs: List of job listings
            
        Returns:
            Jobs sorted by relevance score
        """
        if not jobs:
            return []
        
        logger.info(f"🧮 Computing semantic similarity for {len(jobs)} jobs...")

        # Generate query embedding
        query_embedding = self.embedder.encode(query, convert_to_numpy=True)

        # Generate job embeddings
        job_texts = [
            f"{job.title} {job.snippet}"
            for job in jobs
        ]

        job_embeddings = self.embedder.encode(job_texts, convert_to_numpy=True, show_progress_bar=False)

        # Compute cosine similarity
        for i, job in enumerate(jobs):
            similarity = dot(query_embedding, job_embeddings[i]) / (
                norm(query_embedding) * norm(job_embeddings[i])
            )
            job.relevance_score = float(similarity)
        
        # Sort by relevance score (desc)
        ranked_jobs = sorted(
            jobs,
            key=lambda x: x.relevance_score or 0,
            reverse=True
        )

        logger.info(f"✅ Ranked jobs - top score: {ranked_jobs[0].relevance_score:.3f}")

        return ranked_jobs

    def _format_results(self, jobs: List[JobListing], query: str) -> str:
        """
        Format job results for LLM consumption
        
        Returns a structured string the LLM can understand and present to user
        """
        if not jobs:
            return f"No jobs found matching '{query}'"
        
        result = f"Found {len(jobs)} job opportunities matching '{query}':\n\n"

        for i, job in enumerate(jobs, 1):
            result += f"**Job {i}:** {job.title}\n"
            result += f"**Company:** {job.company}\n"
            result += f"**Location:** {job.location}\n"

            if job.job_type:
                result += f"**Type:** {job.job_type}\n"
            
            if job.salary:
                result += f"**Salary:** {job.salary}\n"
            
            result += f"**Relevance Score:** {job.relevance_score:.2%}\n"
            result += f"**Description:** {job.snippet[:200]}...\n"
            result += f"**Apply:** {job.url}\n"
            result += "\n" + "="*60 + "\n\n"
        
        # Add summary footer
        result += "\n**Search Summary:**\n"
        result += f"- Total jobs: {len(jobs)}\n"
        result += f"- Highest relevance: {jobs[0].relevance_score:.2%}\n"
        result += f"- Average relevance: {sum(j.relevance_score or 0 for j in jobs) / len(jobs):.2%}\n"
        
        return result


def get_job_search_tool(web_search_function) -> JobSearchTool:
    """
    Factory function to create job search tool

    Args:
        web_search_function: Async function to call web search
            Expected signature: async def search(query: str) -> List[Dict]
            
    Returns:
        Configured JobSearchTool instance
    """
    return JobSearchTool(web_search_function=web_search_function)