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

def clean_thinking_tags(text: str) -> str:
    """Remove thinking tags from LLM output"""
    if not text:
        return text
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()

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
        response_text = clean_thinking_tags(response_text)

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
    # mcp_server_tools = [get_mcp_tools()]
    # local_tools = [get_job_search_tool(web_search_function=search_web)]   
    # tools = mcp_server_tools + local_tools

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

    return response_text

async def _langchain_with_streaming(
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

    stream_queue = asyncio.Queue()

    async def mcp_status_handler(msg:str):
       await stream_queue.put({'type': 'status', 'content': msg})

    mcp_client = get_mcp_client()
    raw_mcp_tools = await get_mcp_tools()
    mcp_tools = [
        mcp_client._convert_to_langchain_tool(tool, on_status=mcp_status_handler) for tool in raw_mcp_tools]
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

    # --- Streaming State ---
    async def run_agent():
        tool_was_called = False
        llm_call_count = 0

        try:
            async for event in executor.astream_events(
                {
                    "input": prompt,
                    "chat_history": langchain_history,
                    "current_date": datetime.now().strftime("%y-%m-%d")
                },
                version="v2",
                config={"callbacks": [token_tracker, langfuse_handler]}
            ):
                kind = event["event"]

                if kind == "on_chat_model_start":
                    llm_call_count += 1

                elif kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        if not tool_was_called or (tool_was_called and llm_call_count >=2):
                            await stream_queue.put({"type":"token", "content": content})

                elif kind == "on_tool_start":
                    tool_was_called = True
                    await stream_queue.put({"type": "status", "content": f"Starting tool - {event['name']}..."})

                elif kind == "on_tool_end":
                    await stream_queue.put({"type": "status", "content": "Finished"})
            await stream_queue.put(None)

        except Exception as e:
            logger.error(f"{log_prefix} Agent Error: {e}")
            await stream_queue.put({"type": "error", "content": "Generation failed."})
            await stream_queue.put(None)

    asyncio.create_task(run_agent())

    while True:
        content = await stream_queue.get()
        if content is None:
            break
        # Structure: data: {"type": "token", "content": "..."}
        yield f"data: {json.dumps(content)}\n\n"

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
                raw_chunks = chunk.split("\n\n")
                for raw_chunk in raw_chunks:
                    if not raw_chunk.strip():
                        continue
                    clean_json = raw_chunk.removeprefix("data: ")
                    data = json.loads(clean_json)
                    if "Starting tool" not in data["content"] and "Finished" not in data["content"]:
                        full_response_content.append(data["content"])

        response_text = "".join(full_response_content)

        await persist_history(user_id, chat_id, prompt, log_prefix, response_text, False)

    except (ConnectionError, RuntimeError) as e:
        error_message = "LLM inference failed for session"
        await persist_history(user_id, chat_id, prompt, log_prefix, error_message, True)
        yield "I'm sorry, an error occurred during generation."

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
    full_response_content = []

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
