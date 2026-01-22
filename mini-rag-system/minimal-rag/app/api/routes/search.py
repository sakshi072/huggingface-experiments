"""
Search and query endpoints
"""
import time
import logging

from fastapi import APIRouter, HTTPException, Depends

from app.api.dependencies import get_vectore_storage_retrieval
from app.core import require_scope, extract_scopes
from app.schemas import SearchRequest, SearchResponse, SourceReference, SearchHistory, SearchResult
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Query"])

@router.post("", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    token: dict = Depends(require_scope("search:knowledge"))
):
    """
    Query the Vector Storage and Retrieval system with semantic search.
    Search knowledge base (requires 'search:knowledge' scope)

    Process:
    1. Convert query to embedding
    2. Search PostgreSQL vector database (pgvector)
    3. Retrieve top-k most similar chunks
    4. Return sources with citations

    Parameters:
    - query: Your question (3-500 characters)
    - top_k: Number of chunks to retrieve (1-10, default 3)

    Returns:
    - Source citations with:
      - Document filename
      - Similarity score
      - Text preview

    Security:
    - Requires valid JWT token
    - Token must have 'search:knowledge' scope
    """
    vectore_storage_retrieval = get_vectore_storage_retrieval()
    if vectore_storage_retrieval is None:
        raise HTTPException(
            status_code=503,
            detail="Vector Storage and Retrieval system not initialized"
        )

    try:
        client_id = token.get("sub", "unknown")
        scopes = extract_scopes(token)

        logger.info(
            f"Search request from client: {client_id}, scopes: {scopes}"
        )

        start_time = time.time()

        result = await vectore_storage_retrieval.search(
            query_text=request.query,
            top_k=request.top_k
        )

        query_time = time.time() - start_time

        # Check if we got results
        if not result.get("sources"):
            return SearchResponse(
                sources=[],
                query_time=round(query_time, 2)
            )

        # Format sources
        sources = [
            SourceReference(
                text=source["text"],
                similarity=round(source["similarity"], 3),
                file_url=source["file_url"]
            )
            for source in result["sources"]
        ]

        return SearchResponse(
            sources=sources,
            query_time=round(query_time, 2),
            search_id=str(result["search_id"])
        )

    except Exception as e:
        logger.error(f"Search error: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )

@router.get("", response_model=SearchHistory)
async def search_history(
    limit:int = 10, 
    offset:int = 0,
    token: dict = Depends(require_scope("search:knowledge")
    )):
    """
    List all Query Search Results.

    Parameters:
    - limit: Max documents to return (default 10)
    - skip: Number of documents to skip (for pagination)

    Returns Search History with:
    - Search ID
    - Query Text
    - Chunks 
    - Embedding time
    - DB search time
    - Processing time
    - Created at
    """
    vector_storage_retrieval = get_vectore_storage_retrieval()
    if vector_storage_retrieval is None:
        raise HTTPException(
            status_code=503,
            detail="Vector Storage and Retrieval system not initialized"
        )
    
    try:
        client_id = token.get("sub", "unknown")
        scopes = extract_scopes(token)

        logger.info(
            f"Search request from client: {client_id}, scopes: {scopes}"
        )

        results = await vector_storage_retrieval.search_history(limit, offset)

        return SearchHistory(
            search_history=results
        )
        
    except Exception as e:
        logger.error(f"Search error: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing history: {str(e)}"
        )

@router.get("/{search_id}", response_model=SearchResult)
async def search_history_by_search_id(
    search_id:str,
    token: dict = Depends(require_scope("search:knowledge"))
    ):
    """
    Query Search Results.

    Parameters:
    - search_id

    Returns Search History with:
    - Search ID
    - Query Text
    - Chunks 
    - Embedding time
    - DB search time
    - Processing time
    - Created at
    """
    vector_storage_retrieval = get_vectore_storage_retrieval()
    if vector_storage_retrieval is None:
        raise HTTPException(
            status_code=503,
            detail="Vector Storage and Retrieval system not initialized"
        )
    
    try:
        client_id = token.get("sub", "unknown")
        scopes = extract_scopes(token)

        logger.info(
            f"Search request from client: {client_id}, scopes: {scopes}"
        )
        result = await vector_storage_retrieval.get_search_history_by_id(search_id)

        return result
        
    except Exception as e:
        logger.error(f"Search error: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing history: {str(e)}"
        )
