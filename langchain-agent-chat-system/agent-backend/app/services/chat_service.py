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
from langchain_core.messages import HumanMessage, AIMessage
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from langfuse.langchain import CallbackHandler
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from langchain_core.runnables import RunnableWithFallbacks

from app.core.config import (
   TEMPERATURE
)
from app.models import HistoryMessage
from app.infrastructure.database.repository.chat_repository import MONGO_CHAT_CLIENT
from app.tools.langchain_rag_tool import search_knowledge_base
from app.tools.job_search_tool import get_job_search_tool
from app.clients.web_search_client import search_web
from app.infrastructure.observability.token_tracker import SimpleTokenTracker
from app.infrastructure.observability.request_logger import RequestLogger
from langgraph.checkpoint.memory import MemorySaver
from app.clients.mcp_client import get_mcp_tools, get_mcp_client
import asyncio

load_dotenv()

logger = logging.getLogger("LangChainBackend")
memory = MemorySaver()

# Tool schema cache - avoid list_tools() on every request
_tool_schema_cache: Optional[List] = None
_tool_schema_cache_time: float = 0.0
_TOOL_CACHE_TTL: int = 300
_tool_cache_lock = asyncio.Lock()

def _clean_thinking_tags(text: str) -> str:
    """Remove thinking tags from LLM output"""
    if not text:
        return text
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()

def _convert_mongo_to_langchain(mongo_messages: List[HistoryMessage]) -> List:
    """
    Convert MongoDB history to LangChain format

    Args:
        mongo_messages: List of HistoryMessage from MongoDB

    Returns:
        List of LangChain messages
    """
    langchain_messages = []

    for msg in mongo_messages:
        if msg.role == "user":
            langchain_messages.append(HumanMessage(content=msg.content))
        elif msg.role == 'assistant':
            langchain_messages.append(AIMessage(content=msg.content))

    return langchain_messages

def _make_notification_handler(notification_queue: asyncio.Queue):
    """
    Returns an MCP message handler that forwards ctx.info()
    notifications from the tool into the stream queue.
    """
    async def handler(message) -> None:
        if isinstance(message, Exception):
            logger.error(f"MCP session error: {message}")
            return
        method = getattr(message, 'method', None)
        if not method:
            return
        if "logging/message" in method:
            params = getattr(message, 'params', {})
            data = getattr(params, 'data', '')
            level = getattr(params, 'level', 'info')
            if data:
                logger.info(f"MCP notification [{level}]: {data}")
                await notification_queue.put({
                    "type": "status",
                    "content": str(data)
                })

    return handler

def _build_llm_with_fallback(token_tracker:SimpleTokenTracker) -> RunnableWithFallbacks:
    """
    Primary: local qwen3:8b
    Fallback: faster smaller model
    """
    primary_llm = ChatOllama(
        model="qwen3:8b", # Ensure you have run 'ollama pull llama3.1'
        temperature=TEMPERATURE,
        base_url="http://localhost:9999",
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
    agent_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a helpful assistant. "
            "Use tools when the user asks for specific information from the knowledge base or job listings. "
            "For greetings or general conversation, respond directly without tools."
        )),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=agent_prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=2,
        early_stopping_method="force",
        return_intermediate_steps=True,
    )
async def _get_cached_tool_schemas(session: ClientSession) -> List:
    """Return cached tool schemas if within TTL else fallback to list tools() if expired or empty"""
    global _tool_schema_cache, _tool_schema_cache_time
    current_time = asyncio.get_event_loop().time()

    if _tool_schema_cache and (current_time - _tool_schema_cache_time < _TOOL_CACHE_TTL):
        return _tool_schema_cache
    
    async with _tool_cache_lock:
        if _tool_schema_cache and (asyncio.get_event_loop().time() - _tool_schema_cache_time < _TOOL_CACHE_TTL):
            return _tool_schema_cache
        
        logger.info("Tool schema cache miss - fetching from MCP server")
        tools = await load_mcp_tools(session)
        _tool_schema_cache = tools
        _tool_schema_cache_time = asyncio.get_event_loop().time()
        logger.info(f"Tool schema cache upadteL {len(tools)} tools")
        return _tool_schema_cache
    
async def get_chat_history(user_id:str, chat_id:str, log_prefix:str):
    """Get chat history for a user's chat session"""
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

    history_messages, _, _ = await run_in_threadpool(
        MONGO_CHAT_CLIENT.get_history,
        chat_id,
        limit=15,
        cursor=None
    )
    
    return history_messages

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
    mongo_history: List[HistoryMessage],
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
    langchain_history = _convert_mongo_to_langchain(mongo_history)

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
            "chat_history": langchain_history,
            "current_date": datetime.now().strftime("%y-%m-%d")
        },
        config={"callbacks": [token_tracker, langfuse_handler]}
    )

    response_text = result["output"]
    logger.info("----------------------")
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

async def _langchain_with_streaming(chat_id, prompt, mongo_history, log_prefix):
    token_tracker = SimpleTokenTracker(log_prefix=log_prefix)
    langfuse_handler = CallbackHandler()
    langchain_history = _convert_mongo_to_langchain(mongo_history)
    # notification_queue = asyncio.Queue()
    mcp_client = get_mcp_client()
    client = MultiServerMCPClient(mcp_client._server_config())

    # Connection opens here, stays alive for full agent execution, closes on exit
    try:
        async with client.session("knowledge") as session:
            
            # handler = _make_notification_handler(notification_queue)
            # if hasattr(session, '_message_handler'):
            #     session._message_handler = handler
            #     logger.info("MCP notification handler injected successfully")
            # else:
            #     logger.warning("MCP session does not support _message_handler — ctx.info() notifications will not be forwarded to user")

            raw_tools = await _get_cached_tool_schemas(session)
            logger.info(f"Tools returned from MCP adapter - {raw_tools}")
            tools = [get_job_search_tool(web_search_function=search_web)] + raw_tools

            # llm = ChatOllama(
            #     model="qwen3:8b", # Ensure you have run 'ollama pull llama3.1'
            #     temperature=TEMPERATURE,
            #     base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            #     callbacks=[token_tracker, RequestLogger()]
            # )
            llm = _build_llm_with_fallback(token_tracker)
            executor = _build_agent(llm, tools)
            sent_any = False

            try:
                async for event in executor.astream_events(
                    {"input": prompt, "chat_history": langchain_history},
                    version="v2",
                    config={"callbacks": [token_tracker, langfuse_handler]}
                ):
                    # while not notification_queue.empty():
                    #     notification = notification_queue.get_nowait()
                    #     sent_any = True
                    #     logger.info(f"NOTIFICATION FROM MCP SERVER: {notification}")
                    #     yield f"data: {json.dumps(notification)}\n\n"

                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        content = event["data"]["chunk"].content
                        if content:
                            sent_any = True
                            payload = {'type': 'token', 'content': content}
                            yield f"data: {json.dumps(payload)}\n\n"
                    elif kind == "on_tool_start":
                        sent_any = True
                        tool_input = event.get("data", {}).get("input", {})
                        query = tool_input.get("query", "")
                        payload = {'type': 'status', 'content': f"Searching knowledge base for '{query}'..." if query else "Searching..."}
                        yield f"data: {json.dumps(payload)}\n\n"
                    elif kind == "on_tool_end":
                        # while not notification_queue.empty():
                        #     notification = notification_queue.get_nowait()
                        #     yield f"data: {json.dumps(notification)}\n\n"
                        payload = {'type': 'status', 'content': 'Finished'}
                        yield f"data: {json.dumps(payload)}\n\n"
                
            except Exception as e:
                logger.error(f"{log_prefix} Agent error: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': 'Generation failed.'})}\n\n"
            
            if not sent_any:
                fallback = {"type": "token", "content": "I'm sorry, I couldn't generate response. Please try again."}
                yield f"data: {json.dumps(fallback)}\n\n"
    except Exception as e:
        logger.error(f"{log_prefix} MCP Connection or Setup failed: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'token', 'content': 'I could not generate a response. Please try again.'})}\n\n"

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

    history_messages = await get_chat_history(user_id, chat_id, log_prefix)
    full_response_content = []
    had_error = False
    try:
        async for chunk in _langchain_with_streaming(
            chat_id=chat_id,
            prompt=prompt,
            mongo_history=history_messages,
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

    history_messages = await get_chat_history(user_id, chat_id, log_prefix)

    try:
        response_text = await _langchain_without_streaming(
            chat_id=chat_id,
            prompt=prompt,
            mongo_history=history_messages,
            log_prefix=log_prefix
        )

        await persist_history(user_id, chat_id, prompt, log_prefix, response_text, False)
        return response_text

    except (ConnectionError, RuntimeError) as e:
        error_message = "LLM inference failed for session"
        await persist_history(user_id, chat_id, prompt, log_prefix, error_message, True)
        return error_message
