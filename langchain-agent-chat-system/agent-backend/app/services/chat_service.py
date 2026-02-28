"""Chat service - handles message generation and response logic."""
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Optional
import json
import re
import os
import logging
from datetime import datetime
import time
from dotenv import load_dotenv

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from mcp import ClientSession
from langchain_core.runnables import RunnableWithFallbacks
from app.core.config import (
   TEMPERATURE
)
from app.models import HistoryMessage
from app.infrastructure.database.repository.chat_repository import MONGO_CHAT_CLIENT
from app.tools.job_search_tool import get_job_search_tool
from app.clients.web_search_client import search_web
from app.infrastructure.observability.token_tracker import SimpleTokenTracker
from app.infrastructure.observability.request_logger import RequestLogger
from app.infrastructure.memory.postgres_checkpointer import get_checkpointer
from app.services.chat_history_service import prepare_chat_history
from app.clients.mcp_client import get_mcp_tools, get_mcp_client
import asyncio

load_dotenv()

logger = logging.getLogger("LangChainBackend")
_memory = MemorySaver()

# Tool schema cache - avoid list_tools() on every request
_raw_tool_definition_cache: Optional[List] = None
_raw_tool_definition_cache_time: float = 0.0
_TOOL_CACHE_TTL: int = 300
_tool_cache_lock = asyncio.Lock()

def _clean_thinking_tags(text: str) -> str:
    """Remove thinking tags from LLM output"""
    if not text:
        return text
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()

def _build_llm_with_fallback(token_tracker:SimpleTokenTracker) -> RunnableWithFallbacks:
    """
    Primary: local qwen3:8b
    Fallback: faster smaller model
    """
    primary_llm = ChatOllama(
        model="qwen3:8b", # Ensure you have run 'ollama pull llama3.1'
        temperature=TEMPERATURE,
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        callbacks=[token_tracker, RequestLogger()],
        timeout=30,
    )

    fallback_llm = ChatOllama(
        model="llama3.1:8b", # Ensure you have run 'ollama pull llama3.1'
        temperature=TEMPERATURE,
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        callbacks=[token_tracker, RequestLogger()],
        timeout=20, 
    )

    return primary_llm.with_fallbacks(
        [fallback_llm],
        exceptions_to_handle=(Exception,)
    )
    
def _build_agent(llm, tools):
    """Build agent and executor - separated for clarity"""
    checkpointer = get_checkpointer()
    return create_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        system_prompt=(
            "You are a helpful assistant. "
            "Use tools when the user asks for specific information. "
            "When calling search_docs, select domain_name based ONLY on the current user question. "
            "For greetings or general conversation, respond directly without tools."
        )
    )

def _make_memory_config(chat_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": chat_id,
            "checkpoint_ns": "",
        }
    }

async def _get_raw_cached_tool_definitions(session: ClientSession) -> List:
    """Return cached tool schemas if within TTL else fallback to list tools() if expired or empty"""
    global _raw_tool_definition_cache, _raw_tool_definition_cache_time
    current_time = asyncio.get_event_loop().time()

    if _raw_tool_definition_cache and (current_time - _raw_tool_definition_cache_time < _TOOL_CACHE_TTL):
        return _raw_tool_definition_cache
    
    async with _tool_cache_lock:
        if _raw_tool_definition_cache and (asyncio.get_event_loop().time() - _raw_tool_definition_cache_time < _TOOL_CACHE_TTL):
            return _raw_tool_definition_cache
        
        logger.info("Raw definition cache miss - fetching from MCP server")
        response = await session.list_tools()
        _raw_tool_definition_cache = response.tools
        _raw_tool_definition_cache_time = asyncio.get_event_loop().time()
        logger.info(f"Tool schema cache upadteL {len(_raw_tool_definition_cache)} tools")
        return _raw_tool_definition_cache

async def _build_tools_for_session(session: ClientSession) -> List:
    """Schemas from cache, execution in this session"""
    raw_definitions = await _get_raw_cached_tool_definitions(session)
    return [convert_mcp_tool_to_langchain_tool(session, d) for d in raw_definitions]

async def persist_history(user_id:str, chat_id:str, prompt:str, log_prefix:str, response_text:str, error: bool):
    """Store user and assistant message into db for context"""
    if not response_text:
        logger.error(f"{log_prefix} Empty response!")
        response_text = "I apologize, but I wasn't able to generate a response. Please try again."

    if not error:
        response_text = _clean_thinking_tags(response_text)

    user_message = HistoryMessage(
        session_id=chat_id,
        role="user",
        content=prompt
    )
    
    assistant_message = HistoryMessage(
        session_id=chat_id,
        role="assistant",
        content=response_text
    )

    await run_in_threadpool(
        MONGO_CHAT_CLIENT.save_messages,
        chat_id,
        user_id,
        [user_message, assistant_message]
    )

    logger.info(f"{log_prefix} Successfully generated and stored response.")
            
async def _langchain_without_streaming(
    chat_id: str,
    prompt: str,
    prepared_history,
    log_prefix: str
):
    """
    Enhanced LangChain agent with job search capability

    Args:
        chat_id: Chat session ID
        prompt: User message
        mongo_history: Chat history from MongoDB
        log_prefix: Logging prefix

    Returns:
        Generated response text
    """

    logger.info(f"{log_prefix} Using LangChain agent...")

    token_tracker = SimpleTokenTracker(log_prefix=log_prefix)
    langfuse_handler = CallbackHandler()

    llm = ChatOllama(
        model="llama3.1:8b", # Ensure you have run 'ollama pull llama3.1'
        temperature=TEMPERATURE,
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        callbacks=[token_tracker, RequestLogger()]
    )

    mcp_client = get_mcp_client()
    raw_mcp_tools = await get_mcp_tools()
    mcp_tools = [
        mcp_client._convert_to_langchain_tool(tool) for tool in raw_mcp_tools]
    tools = [get_job_search_tool(web_search_function=search_web)] + mcp_tools

    # Tool schemas are automatically included by create_openai_tools_agent
    # Keep system prompt minimal to reduce tokens
    agent_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a helpful assistant. Use tools when needed for specific information.
For greetings or general conversation, respond directly without tools."""),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    agent = create_openai_tools_agent(
        llm=llm,
        tools=tools,
        prompt=agent_prompt,
    )

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=2,
        early_stopping_method="force",
        return_intermediate_steps=True,
        callbacks=[token_tracker]
    )

    # Using ainvoke to execute agent
    result = await executor.ainvoke(
        {
            "input": prompt,
            "chat_history": prepared_history,
            "current_date": datetime.now().strftime("%y-%m-%d")
        },
        config={"callbacks": [token_tracker, langfuse_handler]}
    )

    response_text = result["output"]
    logger.info(f"response_text after generation: {response_text}")
    steps = result.get("intermediate_steps", [])
    rag_calls = len([s for s in steps if s[0].tool == "search_knowledge_base"])
    job_calls = len([s for s in steps if s[0].tool == "search_jobs"])

    logger.info(
        f"{log_prefix} Agent response generated "
        f"(RAG calls: {rag_calls}, Job searches: {job_calls})"
    )

    totals = token_tracker.get_totals()
    logger.info(
        f"{log_prefix} Token usage: "
        f"{totals['input_tokens']} in + {totals['output_tokens']} out = "
        f"{totals['total_tokens']} total"
    )

    return _clean_thinking_tags(response_text)

async def _langchain_with_streaming(chat_id, prompt, log_prefix):
    token_tracker = SimpleTokenTracker(log_prefix=log_prefix)
    langfuse_handler = CallbackHandler()
    mcp_client = get_mcp_client()
    client = MultiServerMCPClient(mcp_client._server_config())

    checkpointer = get_checkpointer()
    config = _make_memory_config(chat_id)
    existing = await checkpointer.aget_tuple(config)
    
    if existing is not None:
        messages_in_memory = existing.checkpoint.get("channel_values", {}).get("messages", [])
        logger.info(f"{log_prefix} Postgres memory warm: {len(messages_in_memory)} messages")
        for m in messages_in_memory:
            logger.info(f"{log_prefix}   [{m.type}]: {str(m.content)[:80]}")
    else:
        logger.info(f"{log_prefix} Memory cold — loading history from MongoDB for this request")

    # Connection opens here, stays alive for full agent execution, closes on exit
    try:
        async with client.session("knowledge") as session:
            mcp_tools = await _build_tools_for_session(session)
            logger.info(f"Tools returned from MCP adapter - {mcp_tools}")
            tools = [get_job_search_tool(web_search_function=search_web)] + mcp_tools

            llm = _build_llm_with_fallback(token_tracker)
            agent = _build_agent(llm, tools)
            
            tool_called = False
            sent_any = False

            try:
                async for event in agent.astream_events(
                    {"messages":[HumanMessage(content=prompt)]},
                    version="v2",
                    config={
                        **_make_memory_config(chat_id),
                        "callbacks": [token_tracker, langfuse_handler],
                        "recursion_limit": 10},
                ):

                    kind = event["event"]
                    node = event.get("metadata", {}).get("langgraph_node", "")

                    if kind in ("on_chat_model_start", "on_chat_model_stream"):
                        logger.debug(f"LLM event node='{node}' kind='{kind}'")

                    if kind == "on_tool_start":
                        tool_called = True
                        sent_any = True
                        tool_input = event.get("data", {}).get("input", {})
                        logger.info(f"{log_prefix} Tool: {event.get('name')} args={tool_input}")
                        query = tool_input.get("query", "")
                        payload = {'type': 'status', 'content': f"Searching for '{query}'..." if query else "Searching..."}
                        yield f"data: {json.dumps(payload)}\n\n"

                    elif kind == "on_tool_end":
                        tool_called = False
                        logger.info(f"{log_prefix} Tool result: {str(event.get('data', {}).get('output', ''))[:200]}")
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Finished'})}\n\n"

                    elif kind == "on_chat_model_stream" and not tool_called:
                        content = event["data"]["chunk"].content
                        if content:
                            sent_any=True
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                
            except Exception as e:
                logger.error(f"{log_prefix} Agent error: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': 'Generation failed.'})}\n\n"
            
            saved = await checkpointer.aget_tuple(config)
            if saved:
                saved_msgs = saved.checkpoint.get("channel_values", {}).get("messages", [])
                logger.info(f"{log_prefix} Postgres checkpoint: {len(saved_msgs)} messages saved")
            else:
                logger.warning(f"{log_prefix} No checkpoint saved to Postgres")
            if not sent_any:
                yield f"data: {json.dumps({'type': 'token', 'content': 'I could not generate a response. Please try again.'})}\n\n"

    except Exception as e:
        logger.error(f"{log_prefix} MCP Connection or Setup failed: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'content': 'Search services unavailable.'})}\n\n"

async def generate_response_stream(
    user_id: str,
    chat_id: str,
    prompt: str,
    request_id: str,
    correlation_id: str,
):
    """
    Generate response with Langchain streaming

    Args:
        user_id: User ID
        chat_id: Chat session ID
        prompt: User message
        request_id: Request ID for logging
        correlation_id: Correlation ID for logging
        use_langchain: If True, use LangChain agent; if False, use original logic

    Returns:
        Yield response chunks
    """

    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"
    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership,
        chat_id,
        user_id
    )

    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized access attempt - user does not own this chat")
        raise HTTPException(
            status_code=403,
            detail="Unauthorized access to chat session"
        )
    # prepared_messages = await prepare_chat_history(
    #     user_id=None,
    #     chat_id=chat_id,
    #     log_prefix=log_prefix
    # )
    # history_messages = prepared_messages.langchain_messages
    full_response_content = []
    had_error = False
    try:
        async for chunk in _langchain_with_streaming(
            chat_id=chat_id,
            prompt=prompt,
            log_prefix=log_prefix
        ):
            yield chunk

            # Strip SSE format and only collect actual content for DB storage
            if chunk.startswith("data: "):
                try:
                    clean_json = chunk.removeprefix("data: ").strip()
                    if not clean_json:
                        continue
                    
                    data = json.loads(clean_json)
                    msg_type = data.get("type")
                    content = data.get("content", "")
                    
                    if msg_type=="token":
                        full_response_content.append(content)
                    elif msg_type=="error":
                        had_error = True
                except json.JSONDecodeError:
                    continue

        response_text = "".join(full_response_content)
        if not response_text and had_error:
            response_text = "I encountered an error while searching for your answer."
        await persist_history(user_id, chat_id, prompt, log_prefix, response_text, False)

    except Exception as e:
        logger.exception(f"{log_prefix} Stream generation totally failed")
        error_message = f"I'm sorry, I encountered an error: {str(e)}"
        await persist_history(user_id, chat_id, prompt, log_prefix, error_message, True)
        error_payload = {"type": "error", "content": f"System error: {str(e)}"}
        yield f"data: {json.dumps(error_payload)}\n\n"

async def generate_response_standard(
    user_id: str,
    chat_id: str,
    prompt: str,
    request_id: str,
    correlation_id: str,
):
    """
    Generate response for standard LLM call without streaming

    Args:
        user_id: User ID
        chat_id: Chat session ID
        prompt: User message
        request_id: Request ID for logging
        correlation_id: Correlation ID for logging

    Returns:
        Generated response text
    """

    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"
    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership,
        chat_id,
        user_id
    )

    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized access attempt - user does not own this chat")
        raise HTTPException(
            status_code=403,
            detail="Unauthorized access to chat session"
        )
    history_messages = await prepare_chat_history(
        user_id=None,
        chat_id=chat_id,
        log_prefix=log_prefix
    )

    try:
        response_text = await _langchain_without_streaming(
            chat_id=chat_id,
            prompt=prompt,
            prepared_history=history_messages,
            log_prefix=log_prefix
        )

        await persist_history(user_id, chat_id, prompt, log_prefix, response_text, False)
        return response_text

    except (ConnectionError, RuntimeError) as e:
        error_message = "LLM inference failed for session"
        await persist_history(user_id, chat_id, prompt, log_prefix, error_message, True)
        return error_message
