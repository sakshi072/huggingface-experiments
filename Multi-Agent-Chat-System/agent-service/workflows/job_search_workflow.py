from typing import List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.types import Command, RetryPolicy
from langchain.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from models import JobSearchState, JobListing, ExpandedQueryList
from sentence_transformers import SentenceTransformer
import numpy as np
from clients.web_search_client import get_search_client
import logging
import json
import asyncio
import re

logger = logging.getLogger(__name__)

# Global Embedder cache
_embedder = None
search_semaphore = asyncio.Semaphore(5)

# Job board sites that allow crawling and have real job postings
JOB_BOARD_SITES = [
    "site:greenhouse.io",
    "site:lever.co",
    "site:jobs.ashbyhq.com",
    "site:myworkdayjobs.com",
    "site:boards.greenhouse.io",
    "site:jobs.lever.co",
]

"""Query expansion workflow using LLM."""
async def expand_query_node(state: JobSearchState) -> Dict:
    """
    Expand user query into multiple optimized search queries.

    Uses LLM to generate semantically related queries, then combines
    them with site-specific filters to target actual job postings
    on company ATS systems (Greenhouse, Lever, Workday, etc.)
    """
    try:
        user_query = state.get("user_query")
        llm = ChatOllama(
            model="llama3.1:8b",
            temperature=0.8
        )

        structured_llm = llm.with_structured_output(ExpandedQueryList)

        system_prompt = """
        You are a job search query optimization expert.
        Your task is to expand a user's job search query into simplified, clean search terms.

        Focus on:
        - Core job title variations (e.g., "AI Engineer", "Machine Learning Engineer")
        - Location if specified
        - Seniority level variations (Senior, Staff, Lead)

        DO NOT include:
        - Site filters (site:)
        - Complex boolean operators
        - Quotes or special characters

        Generate 2-3 clean, simple queries maximum.
        Example: "Senior Machine Learning Engineer San Francisco"
        """

        user_prompt = f"""Original query: "{user_query}"
        Expand this into clean job search queries."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        response = await structured_llm.ainvoke(messages)

        logger.info(f"LLM expanded queries: {response}")

        base_queries = response.expanded_queries if response.expanded_queries else [user_query]

        # Combine each base query with site filters for targeted search
        expanded_queries = []
        for base_query in base_queries[:3]:
            for site_filter in JOB_BOARD_SITES[:4]:
                expanded_queries.append(f"{base_query} {site_filter}")

        # Also add a few queries without site filter for broader results
        expanded_queries.extend(base_queries[:2])

        logger.info(f"Expanded into {len(expanded_queries)} site-targeted queries")

        return {
            "expanded_queries": expanded_queries
        }
    except Exception as e:
        logger.error(f"Query expansion failed: {e}")
        # Fallback: use original query with site filters
        fallback_queries = [f"{state['user_query']} {site}" for site in JOB_BOARD_SITES[:3]]
        fallback_queries.append(state['user_query'])
        return {
            "expanded_queries": fallback_queries,
            "errors": [f"Query expansion error: {str(e)}"]
        }

def get_embedder():
    """Get cached embedding model"""
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _embedder

async def bounded_search(search_client: Any, query: str, max_results: int) -> List[Dict[str, Any]]:
     """
    Executes a job search with rate-limiting (semaphore) and a hard timeout.

    Raises:
        asyncio.TimeoutError: If the search takes longer than 15 seconds.
    """
     async with search_semaphore:
         try:
             results = await asyncio.wait_for(
             search_client.search(query, max_results),
             timeout=15.0
             )
             return results if results else []
         except asyncio.TimeoutError:
             logger.error(f"Job search timeout for query: {query}")
             return []

async def search_jobs_node(state: JobSearchState) -> Dict:
    """
    Execute web searches for all expanded queries.
    
    Searches Tavily for each expanded query and aggregates results.
    """
    # Patterns that usually indicate a "List" page rather than a "Job" page
    BLACKLIST_PATTERNS = [
        r"/search", r"/jobs-at/", r"--in-", r"\?q=", r"/l-", r"/category/", 
        r"/browse", r"/q-", r"Indeed\.com/q-", r"ZipRecruiter\.com/Jobs/"
    ]

    # Phrases that identify a list/aggregator instead of a specific job
    AGGREGATOR_PHRASES = [
        'apply to all', 
        'find job opportunities near you', 
        'sign in', 
        'sign in to view more jobs', 
        '1000+ jobs', 
        'results for',
        'create job alert',
        'jobs in'
    ]

    try:
        expanded_queries = state.get("expanded_queries", [state["user_query"]])
        max_results = state.get("max_results", 5)

        search_client = get_search_client("tavily")
        all_results = []

        tasks = [
            bounded_search(search_client, query, max_results=max_results * 4)
            for query in expanded_queries
        ]

        # Execute all searches in parallel
        result_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Avoid duplicate urls from different search queries
        seen_urls = set()

        # Aggregate results (filter out exceptions)
        for results in result_list:
            if isinstance(results, Exception):
                logger.warning(f"Search failed: {results}")
                continue
            for item in results:
                url = item.get('url', '')
                snippet = item.get('snippet', item.get('content', ''))

                # 1. Check URL against Regex Blacklist
                is_blacklisted_url = any(re.search(p, url, re.IGNORECASE) for p in BLACKLIST_PATTERNS)
                # 2. Check Snippet against Keyword Blacklist
                is_list_page = any(phrase in snippet.lower() for phrase in AGGREGATOR_PHRASES)

                if url and not is_blacklisted_url and not is_list_page and url not in seen_urls:
                    if len(item.get('content', item.get("snippet", ""))) > 50:
                        seen_urls.add(item.get('url'))
                        all_results.append(item)
        
        logger.info(f"Found {len(all_results)} total results from {len(expanded_queries)} queries")

        return {
            "raw_search_results": all_results
        }
    except Exception as e:
        logger.error(f"Job Search failed for: {e}")
        return {
            "errors": [f"Job Search error: {str(e)}"],
            "raw_search_results": []
        }

def calculate_heuristic_score(text: str) -> float:
    """Calculate how much a piece of text looks like a real job post."""

    # Keywords commonly found in real job descriptions
    JOB_MARKERS = [
        "requirements", "responsibilities", "qualifications", "benefits",
        "compensation", "salary range", "401k", "dental", "vision",
        "years of experience", "equal opportunity employer", "apply now"
    ]

    # Keywords that suggest an aggregator/list page (penalize these)
    LIST_MARKERS = [
        "browse jobs", "search results", "create job alert", 
        "sign in to view", "jobs found", "results for"
    ]

    text_lower = text.lower()
    score = 0.0
    
    # +1 for every "Real Job" marker found
    for marker in JOB_MARKERS:
        if marker in text_lower:
            score += 1.0
            
    # -2 for every "List/Aggregator" marker found (stronger penalty)
    for marker in LIST_MARKERS:
        if marker in text_lower:
            score -= 2.0
            
    # Normalize score between 0 and 1 (roughly)
    return max(0, score / len(JOB_MARKERS))

def rerank_jobs_node(state: JobSearchState) -> Dict:
    """
    Quick reranking using embeddings BEFORE expensive LLM parsing.
    
    This is the key optimization:
    1. Compute cheap embeddings for ALL search results
    2. Rank by semantic similarity
    3. Take top N (e.g., top 10-15)
    4. THEN parse only those with expensive LLM
    
    Saves: (total_results - top_n) * LLM_calls
    Example: (50 results - 10 top) = 40 LLM calls saved!
    """
    try:
        raw_results = state.get('raw_search_results', [])
        user_query = state.get('user_query')
        max_results = state.get('max_results', 5)

        if not raw_results:
            return {"ranked_raw_results": []}
        
        if isinstance(raw_results[0], list):
            raw_results = [item for sublist in raw_results for item in sublist]
        
        # Add a check to skip malformed data and Create raw job text representation 
        valid_jobs = []
        jobs_to_embed = []
        for res in raw_results:
            if isinstance(res, dict) and (res.get("snippet") or res.get("content")):
                valid_jobs.append(res)
                jobs_to_embed.append(f"{res.get("title")} {res.get('snippet', res.get("content", ""))}")
        
        if not jobs_to_embed:
            return {"ranked_raw_results": []}
        
        # Get embedder (cached globally)
        embedder = get_embedder()
        
        # Embed query once
        query_embedding = embedder.encode(user_query, convert_to_numpy=True)

        logger.info(f"query_embedding: {query_embedding}")
        logger.info(f"raw_jobs: {jobs_to_embed}")
        # Batch embed all results
        job_embeddings = embedder.encode(
            jobs_to_embed,
            convert_to_numpy = True,
            show_progress_bar=False
        )

        scored_results = []
        for i, job in enumerate(raw_results):
            # 1. Calculate semantic similarity 
            similarity = np.dot(query_embedding, job_embeddings[i]) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(job_embeddings[i])
            )

            # 2. Calculate heuristic score based on content structure
            content_text = job.get('snippet', '') + " " + (job.get('title', ''))
            h_score = calculate_heuristic_score(content_text)

            # 3. Weighted Blend (e.g., 70% semantic, 30% structural)
            # This ensures a very relevant "list" page still loses to a "real" job
            final_score = (similarity * 0.7) + (h_score * 0.3)

            scored_results.append({
                "job": job,
                "score": float(final_score)
            })
        
        # sort by score
        scored_results.sort(key=lambda x: x["score"], reverse=True)

        parse_count = min(max_results+2, len(scored_results))

        logger.info(
            f"✅ Ranked {len(raw_results)} results, "
            f"selected top {parse_count} for parsing "
            f"(saved {len(raw_results) - parse_count} LLM calls!)"
        )
        
        logger.info(f"scored_results: {scored_results[:parse_count]}")
        return {
            "ranked_raw_results": scored_results[:parse_count],
        }
    except Exception as e:
        logger.error(f"Failed to rerank: {e}")
        return {
            "ranked_raw_results": []
        }
        
async def parse_job(raw_job:Dict, ranking_score: float, structured_llm:Any) -> Any:
    """Helper for parallel job parsing"""
    prompt = f"""Extract job details from this search result:

        Title: {raw_job.get('title', 'Unknown')}
        URL: {raw_job.get('url', '')}
        Content: {raw_job.get('content', raw_job.get('snippet', 'No content available'))}

        Extract the job title, company name, location, description, requirements, salary (if mentioned), and job type (Remote/Hybrid/Onsite).
        If information is not available, use empty string or empty list as appropriate.
        """
    try:
        job = await structured_llm.ainvoke(prompt)
        # Ensure the URL from the search result is preserved
        job.url = raw_job.get('url', '')
        job.relevance_score = ranking_score if ranking_score else 0.0
        return job
    except Exception as e:
        logger.warning(f"Failed to parse result {raw_job.get('url')}: {e}")
        return None

async def parse_jobs_node(state: JobSearchState) -> Dict:
    """
    Parse and structure raw search results into JobListing objects.
    
    Uses LLM to extract structured data from search snippets.
    """
    try: 
        ranked_results = state.get("ranked_raw_results", [])
        max_results = state.get("max_results", 5)

        if not ranked_results:
            return {"jobs": [], "final_results": []}
        
        llm = ChatOllama(
            model="llama3.1:8b",
            temperature=0
        )
        jobs = []

        for item in ranked_results:
            logger.info(f"ranked_results url: {item['job'].get('url', 'N/A')}")

        structured_llm = llm.with_structured_output(JobListing)

        # Parse Jobs as per Job Listing model in parallel
        tasks = [parse_job(item["job"], item["score"], structured_llm) for item in ranked_results]
        parsed_jobs = await asyncio.gather(*tasks)

        # Filter out any None values
        for job in parsed_jobs:
            if job is not None:
                jobs.append(job)
        
        logger.info(f"structured jobs: {jobs[:max_results]}")

        logger.info(f"Successfully structured {len(jobs)} jobs")
        return {
            "jobs":jobs,
            "final_results": jobs[:max_results]
        }
    except Exception as e:
        logger.error(f"Job parsing failed: {e}")
        return {
            "errors": [str[e]],
            "jobs": [],
            "final_results": []
        }

def create_job_search_graph():
    """
    Create the complete job search workflow graph.
    
    FLOW:
    1. Expand query → 2. Search jobs → 3. Quick rerank (cheap!) → 
    4. Parse top jobs (expensive, but only top N) → 5. Final selection → END
    
    search → quick rerank → parse ONLY top 15 ($) → select top 5
    
    Token savings: ~80% if searching 50 results for top 5!
    """
    workflow = StateGraph(JobSearchState)

    # Add nodes
    workflow.add_node("expand_query", expand_query_node)
    workflow.add_node("search_jobs", search_jobs_node)
    workflow.add_node("quick_rerank", rerank_jobs_node)
    workflow.add_node("parse_jobs", parse_jobs_node)

    workflow.set_entry_point("expand_query")
    workflow.add_edge("expand_query", "search_jobs")
    workflow.add_edge("search_jobs", "quick_rerank")
    workflow.add_edge("quick_rerank", "parse_jobs")
    workflow.add_edge("parse_jobs", END)

    return workflow.compile()
        

