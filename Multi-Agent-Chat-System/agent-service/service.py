from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Optional, Tuple
from .config import (
    HF_CLIENT, MODEL_ID, 
    SYSTEM_MESSAGE_INFERENCE, logger, MAX_TOKENS, TEMPERATURE
)
from .models import HistoryMessage, ChatSessionMetadata
from .mongodb_client_handler import MONGO_CHAT_CLIENT
from .rag_client import get_rag_client, get_rag_tool_definition, format_tool_response
import json
import re
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from .langchain_rag_tool import search_knowledge_base
from datetime import datetime
import os
from dotenv import load_dotenv
from .web_search_client import search_web
from .job_search_tool import get_job_search_tool
from .token_tracker import SimpleTokenTracker
from.log_llm_request import RequestLogger
from langfuse.langchain import CallbackHandler

load_dotenv()

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
            # tool_choice = "auto", # Let LLM decide
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
                "content":  content,
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
        # Parse arguments
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

            logger.info(f"🔧 Tool Call: search_knowledge_base(query='{query}', top_k={top_k})")

            # Call RAG service
            rag_client = get_rag_client()
            sources = await rag_client.search(query, top_k)

            # Format response
            if sources:
                response = format_tool_response(sources)
                logger.info(f"✅ Tool returned {len(sources)} sources")
                return response
            else:
                logger.warning("Tool returned no sources")
                return "No relevant information found in the knowledge base."

        except Exception as e:
            logger.error(f"❌ Tool call failed: {e}")
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
    chat_id:str,
    prompt:str,
    mongo_history: List[HistoryMessage],
    log_prefix:str
) -> str:
    """
    Enhanced LangChain agent with job search capability
    
    This is an enhanced version of your existing _generate_response_with_langchain
    that includes the job search tool alongside your RAG tool.
    
    Args:
        chat_id: Chat session ID
        prompt: User message
        mongo_history: Chat history from MongoDB
        log_prefix: Logging prefix
        
    Returns:
        Generated response text
    """
    logger.info(f"{log_prefix} 🦜 Using LangChain agent...")

    token_tracker = SimpleTokenTracker(log_prefix=log_prefix)
    
    # Observability
    langfuse_handler = CallbackHandler()

    # 1. Convert MongoDB history to LangChain format
    langchain_history = _convert_mongo_to_langchain(mongo_history)

    # 2. Initialize LangChain components
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        callbacks=[token_tracker, RequestLogger()]
    )

    # 3. Get tools - Both RAG and Job Search
    job_search_tool = get_job_search_tool(web_search_function=search_web)

    tools = [search_knowledge_base, job_search_tool]

    # 3. Create agent prompt
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

    # 4. Create agent
    agent = create_openai_tools_agent(
        llm=llm,
        tools = tools,
        prompt=agent_prompt
    )

    # 6. Create executor
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=2,
        early_stopping_method="force",
        return_intermediate_steps=True,
        callbacks=[token_tracker]
    )

    # 7. Execute with history from MongoDB
    result = await executor.ainvoke(
        {
            "input":prompt,
            "chat_history": langchain_history,
            "current_date": datetime.now().strftime("%y-%m-%d")
        },
        config={"callbacks": [token_tracker, langfuse_handler]}
    )

    # 8. Extract response
    response_text = result["output"]
    steps = result.get("intermediate_steps", [])
    rag_calls = len([s for s in steps if s[0].tool == "search_knowledge_base"])
    job_calls = len([s for s in steps if s[0].tool == "search_jobs"])

    logger.info(
        f"{log_prefix} ✅ Agent response generated "
        f"(RAG calls: {rag_calls}, Job searches: {job_calls})"
    )

    # Log token usage from tracker
    totals = token_tracker.get_totals()
    logger.info(
        f"{log_prefix} 📊 Token usage: "
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

    # 1. Verify user owns this chat
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

    # 2. Get recent history for context (token-optimized: limit to recent messages)
    # Using cursor=None to get most recent messages
    history_messages, _, _ = await run_in_threadpool(
        MONGO_CHAT_CLIENT.get_history,
        chat_id,
        limit=15,  # Reduced from 50 to save tokens
        cursor=None
    )

    # 3. Prepare and append the new user message
    user_message = HistoryMessage(
        session_id=chat_id,
        role="user",
        content=prompt
    )
    history_messages.append(user_message)

    try:
        # 4. DECISION POINT: LangChain or Original?
        if use_langchain:
            # Use langchain agent
            response_text = await _generate_response_with_langchain(
                chat_id=chat_id,
                prompt=prompt,
                mongo_history=history_messages[:-1],
                log_prefix=log_prefix
            )
        else:
            # ORIGINAL PATH: Use your existing logic
            response_text = await _generate_response_original(
                prompt=prompt,
                history_messages=history_messages,
                log_prefix=log_prefix
            )
        
        # 5. Validate response (UNCHANGED)
        if not response_text:
            logger.error(f"{log_prefix} ❌ Empty response!")
            response_text = "I apologize, but I wasn't able to generate a response. Please try again."
        
        response_text = clean_thinking_tags(response_text)

        # 6. Save to MongoDB (UNCHANGED)
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
        # Error handling (UNCHANGED)
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
    Original response generation logic (EXTRACTED from generate_response)
    
    This is your EXISTING code - moved to separate function for clarity
    """

    logger.debug(f"{log_prefix} Appended user message to history.")

    # 1. CRITICAL: Construct the inference context list
    # The context list MUST START with the system message
    inference_context = [SYSTEM_MESSAGE_INFERENCE]

    inference_context.extend([
        msg.to_inference_format()
        for msg in history_messages
    ])

    # 2. Define available tools
    tools = [get_rag_tool_definition()]

    try:
        # 3. Call the synchronous API in a thread pool
        logger.info(f"{log_prefix} 🤖 Calling LLM with tools...")

        first_response = await run_in_threadpool(
            sync_call_hf_api,
            messages=inference_context,
            tools = tools,
            max_tokens = 100
        )

        logger.info("first_response:", first_response)

        # 7. Check if LLM wants to use tools
        if first_response['tool_calls']:
            logger.info(f"{log_prefix} 🔧 LLM requested {len(first_response['tool_calls'])} tool call(s)!")

            # Add LLM's response to context
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

            # 8. Execute each tool call
            for tool_call in first_response['tool_calls']:
                tool_result = await handle_tool_call(tool_call)

                # Add tool result to context
                inference_context.append({
                    "role": "tool",
                    "tool_call_id": getattr(tool_call, 'id', 'call_1'),
                    "name": tool_call.function.name,
                    "content": tool_result
                })
            
            # 9. Second LLM call - generate final answer with tool results
            logger.info(f"{log_prefix} 🤖 Calling LLM with tool results...")

            final_response = await run_in_threadpool(
                sync_call_hf_api,
                messages = inference_context,
                tools = None,
                max_tokens = 100
            )

            response_text = final_response['content']
            logger.info(f"{log_prefix} ✅ Generated response with RAG")
        
        else:
            # No tools needed - use direct response
            response_text = first_response['content']
            logger.info(f"{log_prefix} ✅ Generated response without RAG")
        
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
        detail_msg = f"LLM inference failure. {str(e)}"

        logger.error(f"{log_prefix} Failed to generate response for session: {detail_msg}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "LLM_INFERENCE_FAILED", "message": detail_msg}
        )


async def generate_smart_title(
    user_id: str,
    first_message: str,
    assistant_response: str = None,
    request_id: str = None, 
    correlation_id: str = None
) -> str:
    """
    Uses the LLM to generate a concise, meaningful title for a chat.
    """
    log_prefix = f"[RID:{request_id[:8] if request_id else 'N/A'}] [CID:{correlation_id[:8] if correlation_id else 'N/A'}] [UID:{user_id[:8]}]"
    
    try: 
        if assistant_response:
            title_prompt = (
                f"Based on this conversation, generate a short, concise title (maximum 50 characters):\n\n"
                f"User: {first_message}\n"
                f"Assistant: {assistant_response}\n\n"
                f"Generate ONLY the title, nothing else. Keep it under 50 characters."
            )
        else:
            title_prompt = (
                f"Generate a short, concise title (maximum 50 characters) for a conversation starting with:\n\n"
                f"\"{first_message}\"\n\n"
                f"Generate ONLY the title, nothing else. Keep it under 50 characters."
            )
        
        title_context = [
            {
                "role": "system",
                "content": "You are a helpful assistant that generates concise, descriptive titles for conversations. Respond with ONLY the title, no explanations or extra text."
            },
            {
                "role": "user",
                "content": title_prompt
            }
        ]

        logger.debug(f"{log_prefix} Generating AI title...")

        if HF_CLIENT is None:
            raise ConnectionError("Hugging Face client is not initialized.")

        completion = await run_in_threadpool(
            lambda: HF_CLIENT.chat.completions.create(
                model=MODEL_ID,
                messages=title_context,
                max_tokens=30,
                temperature=0.7,
                stream=False
            )
        )

        generated_title = completion.choices[0].message.content.strip()
        generated_title = generated_title.strip('"\'')

        prefixes_to_remove = ["Title:", "Chat:", "Conversation:"]
        for prefix in prefixes_to_remove:
            if generated_title.startswith(prefix):
                generated_title = generated_title[len(prefix):].strip()

        if len(generated_title) > 50:
            generated_title = generated_title[:47] + "..."
        
        if len(generated_title) < 3:
            logger.warning(f"{log_prefix} Generated title too short, using fallback")
            generated_title = generate_fallback_title(first_message)
        
        logger.info(f"{log_prefix} Generated AI title: '{generated_title}'")
        return generated_title
        
    except Exception as e:
        logger.error(f"{log_prefix} Failed to generate AI title: {e}", exc_info=True)
        return generate_fallback_title(first_message)


def generate_fallback_title(message: str) -> str:
    """
    Generate a fallback title by truncating the message intelligently.
    """
    cleaned = message.strip().replace('\n', ' ').replace('\r', '')
    cleaned = ' '.join(cleaned.split())
    
    if len(cleaned) <= 50:
        return cleaned
    
    truncated = cleaned[:47]
    last_space = truncated.rfind(' ')
    
    if last_space > 30:
        return truncated[:last_space] + '...'
    
    return truncated + '...'


# --- Chat Session Management Functions ---

async def create_chat_session(
    user_id: str,
    title: str,
    request_id: str,
    correlation_id: str
) -> str:
    """Creates a new chat session document in MongoDB."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}]"

    try:
        chat_id = await run_in_threadpool(
            MONGO_CHAT_CLIENT.create_chat_session,
            user_id,
            title
        )

        if not chat_id:
            logger.error(f"{log_prefix} Failed to create chat session - no chat_id returned")
            raise HTTPException(
                status_code=500, 
                detail="Failed to create chat session"
            )

        logger.info(f"{log_prefix} Created new chat session {chat_id[:8]}... with title: {title}")
        return chat_id

    except Exception as e:
        logger.error(f"{log_prefix} Failed to create chat session: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to create chat session: {e}"}
        )


async def get_user_chat_sessions(
    user_id: str,
    request_id: str,
    correlation_id: str,
    limit: int,
    cursor: Optional[str]
) -> Tuple[List[ChatSessionMetadata], Optional[str], bool]:
    """
    Get user's chat sessions with cursor-based pagination
    
    Returns: (sessions, next_cursor, has_more)
    """
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}]"

    try:
        sessions, next_cursor, has_more = await run_in_threadpool(
            MONGO_CHAT_CLIENT.get_user_chat_sessions,
            user_id,
            limit,
            cursor
        )
        logger.info(f"{log_prefix} Retrieved {len(sessions)} chat sessions.")
        return sessions, next_cursor, has_more
    except Exception as e:
        logger.error(f"{log_prefix} Failed to retrieve user sessions: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to retrieve chat sessions: {e}"}
        )


async def delete_chat_session(
    user_id: str,
    chat_id: str,
    request_id: str,
    correlation_id: str
):
    """Deletes a specific chat session for the authenticated user."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"
    
    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership, 
        chat_id, 
        user_id
    )
    
    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized delete attempt - user does not own this chat")
        raise HTTPException(
            status_code=403, 
            detail="Unauthorized: You do not own this chat session"
        )

    try:
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.delete_chat_session,
            chat_id,
            user_id
        )
        logger.info(f"{log_prefix} Chat session deleted successfully.")
    except Exception as e:
        logger.error(f"{log_prefix} Failed to delete chat session: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to delete chat session: {e}"}
        )


async def update_chat_title(
    user_id: str,
    chat_id: str,
    title: str,
    request_id: str,
    correlation_id: str
):
    """Updates the title of a chat session for the authenticated user."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"
    
    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership, 
        chat_id, 
        user_id
    )
    
    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized update attempt - user does not own this chat")
        raise HTTPException(
            status_code=403, 
            detail="Unauthorized: You do not own this chat session"
        )

    try:
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.update_chat_title,
            chat_id,
            user_id,
            title
        )
        logger.info(f"{log_prefix} Chat session title updated to: {title}")
    except Exception as e:
        logger.error(f"{log_prefix} Failed to update chat title: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to update chat title: {e}"}
        )


async def get_history(
    user_id: str,
    chat_id: str,
    request_id: str,
    correlation_id: str,
    limit: int,
    cursor: Optional[str]
) -> Tuple[List[HistoryMessage], Optional[str], bool]:
    """
    Get chat history with cursor-based pagination
    
    Returns: (messages, next_cursor, has_more)
    """
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership, 
        chat_id, 
        user_id
    )
    
    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized history access attempt")
        raise HTTPException(
            status_code=403, 
            detail="Unauthorized: You do not own this chat session"
        )

    try: 
        history_list, next_cursor, has_more = await run_in_threadpool(
            MONGO_CHAT_CLIENT.get_history, 
            chat_id, 
            limit, 
            cursor
        )

        if not history_list:
            logger.info(f"{log_prefix} No history found (empty chat)")
            return [], None, False  # FIXED: Return tuple, not just list
        
        logger.info(f"{log_prefix} Retrieved {len(history_list)} messages")
        return history_list, next_cursor, has_more  # FIXED: Use correct variable name
        
    except Exception as e:
        logger.error(f"{log_prefix} Failed to retrieve history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": "DATABASE_ERROR", 
                "message": "Failed to retrieve chat history from database"
            }
        )


async def clear_history(
    user_id: str, 
    chat_id: str, 
    request_id: str,
    correlation_id: str
):
    """Removes the chat history for a given session ID from MongoDB."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership, 
        chat_id, 
        user_id
    )
    
    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized clear attempt")
        raise HTTPException(
            status_code=403, 
            detail="Unauthorized: You do not own this chat session"
        )

    try:
        await run_in_threadpool(MONGO_CHAT_CLIENT.clear_history, chat_id)
        logger.info(f"{log_prefix} History cleared successfully.")
    except Exception as e:
        logger.error(f"{log_prefix} Failed to clear history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "DATABASE_ERROR", 
                "message": "Failed to clear chat history from database"
            }
        )