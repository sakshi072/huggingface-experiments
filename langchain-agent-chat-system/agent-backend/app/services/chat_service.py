"""Chat service - handles message generation and response logic."""
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Optional
import json
import re
import os
import logging
from datetime import datetime
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

load_dotenv()

logger = logging.getLogger("LangChainBackend")
memory = MemorySaver()

def clean_thinking_tags(text: str) -> str:
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


async def _generate_response_with_langchain(
    chat_id: str,
    prompt: str,
    mongo_history: List[HistoryMessage],
    log_prefix: str
) -> str:
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

    job_search_tool = get_job_search_tool(web_search_function=search_web)

    tools = [search_knowledge_base, job_search_tool]

    agent_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are Ollama, an assistant. Respond concisely to user query as per below categories.
  - search_knowledge_base: internal documents, company policies, uploaded files
  - search_jobs: job openings, career opportunities
  - No tool: greetings, general questions, follow-ups on previous results, eg: Hi, How are you?
  Respond concisely. """),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    agent = create_openai_tools_agent(
        llm=llm,
        tools=tools,
        prompt=agent_prompt
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

    result = await executor.ainvoke(
        {
            "input": prompt,
            "chat_history": langchain_history,
            "current_date": datetime.now().strftime("%y-%m-%d")
        },
        config={"callbacks": [token_tracker, langfuse_handler]}
    )

    response_text = result["output"]
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

    return clean_thinking_tags(response_text)


async def generate_response(
    user_id: str,
    chat_id: str,
    prompt: str,
    request_id: str,
    correlation_id: str,
    use_langchain: bool = False
) -> str:
    """
    Generate response with optional LangChain enhancement

    Args:
        user_id: User ID
        chat_id: Chat session ID
        prompt: User message
        request_id: Request ID for logging
        correlation_id: Correlation ID for logging
        use_langchain: If True, use LangChain agent; if False, use original logic

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

    history_messages, _, _ = await run_in_threadpool(
        MONGO_CHAT_CLIENT.get_history,
        chat_id,
        limit=15,
        cursor=None
    )

    user_message = HistoryMessage(
        session_id=chat_id,
        role="user",
        content=prompt
    )
    history_messages.append(user_message)

    try:
        response_text = await _generate_response_with_langchain(
            chat_id=chat_id,
            prompt=prompt,
            mongo_history=history_messages[:-1],
            log_prefix=log_prefix
        )

        if not response_text:
            logger.error(f"{log_prefix} Empty response!")
            response_text = "I apologize, but I wasn't able to generate a response. Please try again."

        response_text = clean_thinking_tags(response_text)

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
        return response_text

    except (ConnectionError, RuntimeError) as e:
        error_message = HistoryMessage(
            session_id=chat_id,
            role="assistant",
            content="LLM inference failed for session"
        )
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.save_messages,
            chat_id,
            user_id,
            [user_message, error_message]
        )
        raise HTTPException(status_code=500, detail={"error": "LLM_INFERENCE_FAILED"})
