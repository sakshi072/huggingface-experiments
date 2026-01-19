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

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from langfuse.langchain import CallbackHandler

from core.config import (
    HF_CLIENT, MODEL_ID,
    SYSTEM_MESSAGE_INFERENCE, MAX_TOKENS, TEMPERATURE
)
from models import HistoryMessage
from infrastructure.database.repositories.chat_repository import MONGO_CHAT_CLIENT
from clients.rag_client import get_rag_client, get_rag_tool_definition, format_tool_response
from tools.rag_tool import search_knowledge_base
from tools.job_search_tool import get_job_search_tool
from clients.web_search_client import search_web
from infrastructure.observability.token_tracker import SimpleTokenTracker
from infrastructure.observability.request_logger import RequestLogger
from langgraph.checkpoint.memory import MemorySaver
from workflows import create_supervisor_graph

load_dotenv()

logger = logging.getLogger("HuggBackend")
memory = MemorySaver()

def clean_thinking_tags(text: str) -> str:
    """Remove thinking tags from LLM output"""
    if not text:
        return text
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def sync_call_hf_api(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict]] = None,
    max_tokens: int = 100
) -> dict:
    """Performs the synchronous blocking call to the Hugging Face API."""

    if HF_CLIENT is None:
        raise ConnectionError("Hugging Face client is not initialized.")

    logger.debug(f"Calling LLM with {len(messages)} messages and {len(tools or [])} tools")
    try:
        completion = HF_CLIENT.chat.completions.create(
            model=MODEL_ID,
            tools=tools,
            messages=messages,
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            stream=False
        )

        message = completion.choices[0].message

        logger.info(message)

        content = clean_thinking_tags(message.content) if message.content else None

        if hasattr(message, 'tool_calls') and message.tool_calls:
            return {
                "content": content,
                "tool_calls": getattr(message, 'tool_calls', None)
            }
        else:
            return {
                "content": content,
                "tool_calls": None
            }

    except Exception as e:
        logger.error(f"External LLM API Error during call: {e}", exc_info=True)
        raise RuntimeError(f"External LLM API call failed: {e}")


async def handle_tool_call(tool_call) -> str:
    """
    Execute a tool call and return the result

    Args:
        tool_call: Tool call object from LLM

    Returns:
        Formatted tool response
    """
    function_name = tool_call.function.name

    if function_name == 'search_knowledge_base':
        try:
            args = tool_call.function.arguments

            if isinstance(args, str):
                args = json.loads(args)
            elif isinstance(args, dict):
                pass
            else:
                raise ValueError(f"Unexpected arguments type: {type(args)}")
            query = args.get('query', '')
            top_k = args.get('top_k', 3)

            logger.info(f"Tool Call: search_knowledge_base(query='{query}', top_k={top_k})")

            rag_client = get_rag_client()
            sources = await rag_client.search(query, top_k)

            if sources:
                response = format_tool_response(sources)
                logger.info(f"Tool returned {len(sources)} sources")
                return response
            else:
                logger.warning("Tool returned no sources")
                return "No relevant information found in the knowledge base."

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            return f"Error searching knowledge base: {str(e)}"
    else:
        logger.warning(f"Unknown tool: {function_name}")
        return f"Unknown tool: {function_name}"


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

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        callbacks=[token_tracker, RequestLogger()]
    )

    job_search_tool = get_job_search_tool(web_search_function=search_web)

    tools = [search_knowledge_base, job_search_tool]

    agent_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are HUGG, an assistant.
  - search_knowledge_base: internal documents, company policies, uploaded files
  - search_jobs: job openings, career opportunities
  - No tool: greetings, general questions, follow-ups on previous results
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
        if use_langchain:
            response_text = await _generate_response_with_langchain(
                chat_id=chat_id,
                prompt=prompt,
                mongo_history=history_messages[:-1],
                log_prefix=log_prefix
            )
        else:
            response_text = await _generate_response_original(
                prompt=prompt,
                history_messages=history_messages,
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


async def _generate_response_original(
    prompt: str,
    history_messages: List[HistoryMessage],
    log_prefix: str
) -> str:
    """
    Original response generation logic

    This is the existing code - moved to separate function for clarity
    """

    logger.debug(f"{log_prefix} Appended user message to history.")

    inference_context = [SYSTEM_MESSAGE_INFERENCE]

    inference_context.extend([
        msg.to_inference_format()
        for msg in history_messages
    ])

    tools = [get_rag_tool_definition()]

    try:
        logger.info(f"{log_prefix} Calling LLM with tools...")

        first_response = await run_in_threadpool(
            sync_call_hf_api,
            messages=inference_context,
            tools=tools,
            max_tokens=100
        )

        logger.info("first_response:", first_response)

        if first_response['tool_calls']:
            logger.info(f"{log_prefix} LLM requested {len(first_response['tool_calls'])} tool call(s)!")

            inference_context.append({
                "role": "assistant",
                "content": first_response['content'],
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in first_response['tool_calls']
                ]
            })

            for tool_call in first_response['tool_calls']:
                tool_result = await handle_tool_call(tool_call)

                inference_context.append({
                    "role": "tool",
                    "tool_call_id": getattr(tool_call, 'id', 'call_1'),
                    "name": tool_call.function.name,
                    "content": tool_result
                })

            logger.info(f"{log_prefix} Calling LLM with tool results...")

            final_response = await run_in_threadpool(
                sync_call_hf_api,
                messages=inference_context,
                tools=None,
                max_tokens=100
            )

            response_text = final_response['content']
            logger.info(f"{log_prefix} Generated response with RAG")

        else:
            response_text = first_response['content']
            logger.info(f"{log_prefix} Generated response without RAG")

        return response_text

    except (ConnectionError, RuntimeError) as e:
        detail_msg = f"LLM inference failure. {str(e)}"
        logger.error(f"{log_prefix} Failed to generate response for session: {detail_msg}")
        raise HTTPException(
            status_code=500,
            detail={"error": "LLM_INFERENCE_FAILED", "message": detail_msg}
        )

async def execute_supervisor_workflow(
    user_id: str,
    chat_id: str,
    prompt: str,
    request_id: str,
    correlation_id: str,
    max_result: Optional[int] = 5,
    time_window_hours: Optional[int] = 72
) -> str:
    """
    Generate response with workflows

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
    
    # 1. Initialize Graph and Config
    supervisor_graph = create_supervisor_graph(checkpointer=memory)

    langfuse_handler = CallbackHandler()

    config = {
        "configurable": {"thread_id": chat_id},
        "callbacks": [langfuse_handler]
        }

    try: 
        # 2. Check if MemorySaver has a snapshot
        existing_state = await supervisor_graph.aget_state(config)

        if existing_state.values:
            # Memory is warm! We don't need to load from Mongo.
            # We just pass the new message.
            input_data = {
                "messages": [HumanMessage(content=prompt)],
                "user_query": prompt
            }
        else:
            # Memory is cold! Rehydrate from MongoDB
            logger.info(f"Memory cold. Rehydrating chat {chat_id} from MongoDB")

            history_messages, _, _ = await run_in_threadpool(
                MONGO_CHAT_CLIENT.get_history,
                chat_id,
                limit=15,
                cursor=None
            )

            langchain_history = _convert_mongo_to_langchain(history_messages)
            
            # Seed the state with history AND the current prompt
            input_data = {
                "messages": langchain_history + [HumanMessage(content=prompt)],
                "user_query": prompt,
                "max_results": max_result,
                "time_window_hours": time_window_hours,
                "errors": []
            }

        # 3. Invoke the supervisor graph
        result = await supervisor_graph.ainvoke(input_data, config=config)

        logger.info(f"final result: {result}")
        # 4. Extract final answer (last message in the state)
        final_answer = result["messages"][-1].content

        # 5. Persist the new exchange back to MongoDB
        user_message = HistoryMessage(session_id=chat_id, role="user", content=prompt)
        assistant_message = HistoryMessage(session_id=chat_id, role="assistant", content=final_answer)

        await run_in_threadpool(
            MONGO_CHAT_CLIENT.save_messages,
            chat_id,
            user_id,
            [user_message, assistant_message]
        )

        logger.info(f"{log_prefix} Successfully generated and stored response.")
        return final_answer

    except (ConnectionError, RuntimeError) as e:
        error_message = HistoryMessage(
            session_id=chat_id,
            role="assistant",
            content="Workflow failed for session"
        )
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.save_messages,
            chat_id,
            user_id,
            [user_message, error_message]
        )
        raise HTTPException(status_code=500, detail={"error": "Workflow_INFERENCE_FAILED"})
