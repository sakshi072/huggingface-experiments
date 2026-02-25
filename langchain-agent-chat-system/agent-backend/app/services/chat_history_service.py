from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging
from starlette.concurrency import run_in_threadpool
from app.infrastructure.database.repository.chat_repository import MONGO_CHAT_CLIENT
from fastapi import HTTPException
from app.models import HistoryMessage
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
import os

logger = logging.getLogger(__name__)

SUMMARY_THRESHOLD = 14  # summarize when history exceeds this many messages
SUMMARY_KEEP_RECENT = 6 # always keep last N messages verbatim

@dataclass
class PreparedHistory:
    langchain_messages: List
    message_count: int
    was_summarized: bool
    token_estimate: int

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

async def _summarize_history(
    messages: List,
    existing_summary: Optional[str],
    log_prefix:str
) -> str:
    """Compress old messages into a summary, keep recent ones verbatim"""
    llm = ChatOllama(
        model="llama3.1:8b", # Ensure you have run 'ollama pull llama3.1'
        temperature=0,
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:9999"),
    )

    summary_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Summarize the following conversation concisely. "
            "Preserve key facts, decisions, and context. "
            "Be brief - 3-5 sentences maximum."
        )),
        ("human", (
            "{existing_summary}"
            "\n\nNew messages to incorporate:\n{messages}"
        ))
    ])

    chain = summary_prompt | llm
    result = await chain.ainvoke({
        "existing_summary": f"Previous summary: {existing_summary}" if existing_summary else "",
        "messages": "\n".join([
            f"{m.type}: {m.content}" for m in messages
        ])
    })
    return result.content

async def get_compressed_history(mongo_messages:List[HistoryMessage], chat_id:str, log_prefix:str) -> tuple[List, Optional[str]]:
    """
    Returns (langchain_messages, summary_used)
    """
    old_messages = mongo_messages[:-SUMMARY_KEEP_RECENT]
    recent_messages = mongo_messages[-SUMMARY_KEEP_RECENT:]

    summary = await _summarize_history(
        _convert_mongo_to_langchain(old_messages),
        existing_summary=None,
        log_prefix=log_prefix
    )
    logger.info(f"Compressed summary example: {summary}")
    compressed = [
        SystemMessage(content=f"Conversation summary: {summary}")
    ] + _convert_mongo_to_langchain(recent_messages)

    logger.info(f"{log_prefix} Compressed {len(old_messages)} messages into summary")
    return compressed, summary

async def prepare_chat_history(
    user_id: str,
    chat_id: str,
    log_prefix: str
) -> PreparedHistory:
    """
    Single entry point for all history preparation"""

    raw_messages, _, _ = await run_in_threadpool(
        MONGO_CHAT_CLIENT.get_history,
        chat_id,
        limit=20,
        cursor=None
    )

    if not raw_messages:
        return PreparedHistory([],0,False,0)
    
    # Choose strategy based on length
    if len(raw_messages) <= 6:
        # Short history - user verbatim
        messages = _convert_mongo_to_langchain(raw_messages)
        token_estimate = sum(len(m.content.split() * 1.3 for m in raw_messages))
        return PreparedHistory(messages, len(messages), False, int(token_estimate))
    
    elif len(raw_messages) <= 14:
        # Medium history - sliding window, keep last 6
        recent = messages[-6:]
        messages = _convert_mongo_to_langchain(recent)
        token_estimate = sum(len(m.content.split() * 1.3 for m in raw_messages))
        return PreparedHistory(messages, len(messages), False, int(token_estimate))
    
    else:
        # Long history - summarization, keep recent verbatim
        messages, summary = await get_compressed_history(raw_messages, chat_id, log_prefix)
        token_estimate = len(str(messages)) // 4
        logger.info(f"{log_prefix} Used summary compression for {len(raw_messages)}")
        return PreparedHistory(messages, len(messages), True, token_estimate)