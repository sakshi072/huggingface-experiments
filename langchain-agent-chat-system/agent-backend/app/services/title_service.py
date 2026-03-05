"""Title service - handles smart title generation."""
from starlette.concurrency import run_in_threadpool
import logging
from app.core.settings import settings
from app.core.config import HF_CLIENT

logger = logging.getLogger("LangChainBackend")


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
                model=settings.HF_MODEL_ID,
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
