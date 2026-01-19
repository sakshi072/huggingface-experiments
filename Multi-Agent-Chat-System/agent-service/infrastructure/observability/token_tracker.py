from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class SimpleTokenTracker(BaseCallbackHandler):
    def __init__(self, log_prefix: str = ""):
        self.log_prefix = log_prefix
        self.total_input = 0
        self.total_output = 0
        self.call_count = 0

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Track when LLM call starts"""
        self.call_count += 1
        logger.info(f"{self.log_prefix} 🔥 LLM Call #{self.call_count} started")

    def on_llm_end(self, response, **kwargs) -> None:
        """This runs every time the LLM finishes a response"""
        try:
            input_t = 0
            output_t = 0
            
            # Try multiple locations where token usage might be stored
            
            # Method 1: OpenAI format (llm_output)
            if hasattr(response, 'llm_output') and response.llm_output:
                token_usage = response.llm_output.get('token_usage', {})
                if token_usage:
                    input_t = token_usage.get('prompt_tokens', 0)
                    output_t = token_usage.get('completion_tokens', 0)
                    logger.info(f"{self.log_prefix} 📊 Found OpenAI token usage")
            
            # Method 2: Google Gemini format (usage_metadata in message)
            if input_t == 0 and output_t == 0:
                try:
                    usage = response.generations[0][0].message.usage_metadata
                    if usage:
                        input_t = usage.get("input_tokens", 0)
                        output_t = usage.get("output_tokens", 0)
                        logger.info(f"{self.log_prefix} 📊 Found Google token usage")
                except (AttributeError, IndexError, KeyError):
                    pass
            
            # Method 3: Anthropic format (might be in response_metadata)
            if input_t == 0 and output_t == 0:
                try:
                    metadata = response.generations[0][0].generation_info
                    if metadata and 'usage' in metadata:
                        usage = metadata['usage']
                        input_t = usage.get('input_tokens', 0)
                        output_t = usage.get('output_tokens', 0)
                        logger.info(f"{self.log_prefix} 📊 Found Anthropic token usage")
                except (AttributeError, IndexError, KeyError):
                    pass
            
            # If we found tokens, track them
            if input_t > 0 or output_t > 0:
                self.total_input += input_t
                self.total_output += output_t

                print(f"\n{self.log_prefix} 📝 [LLM CALL #{self.call_count}]")
                print(f"   Input:  {input_t:,} tokens")
                print(f"   Output: {output_t:,} tokens")
                print(f"   Subtotal: {input_t + output_t:,} tokens")
                print(f"   Running Total: {self.total_input + self.total_output:,} tokens\n")
            else:
                # Debug: print the response structure to see what we're missing
                logger.warning(f"{self.log_prefix} ⚠️ Could not extract token usage from response")
                logger.debug(f"Response structure: {dir(response)}")
                if hasattr(response, 'llm_output'):
                    logger.debug(f"llm_output: {response.llm_output}")
                
        except Exception as e:
            logger.error(f"{self.log_prefix} ❌ Error tracking tokens: {e}", exc_info=True)

    def on_chain_end(self, outputs, **kwargs) -> None:
        """This runs when the final Agent result is produced"""
        total = self.total_input + self.total_output
        
        print(f"\n{'='*60}")
        print(f"{self.log_prefix} 📈 [FINAL SESSION SUMMARY]")
        print(f"{'='*60}")
        print(f"   Total LLM Calls:     {self.call_count}")
        print(f"   Total Input Tokens:  {self.total_input:,}")
        print(f"   Total Output Tokens: {self.total_output:,}")
        print(f"   Grand Total:         {total:,} tokens")
        
        # Cost estimation (approximate)
        if total > 0:
            # Estimate cost for gpt-4o-mini
            cost = (self.total_input / 1_000_000 * 0.15) + (self.total_output / 1_000_000 * 0.60)
            print(f"   Estimated Cost:      ${cost:.6f} (gpt-4o-mini)")
        
        print(f"{'='*60}\n")

    def get_totals(self) -> Dict[str, int]:
        """Get current token totals"""
        return {
            "input_tokens": self.total_input,
            "output_tokens": self.total_output,
            "total_tokens": self.total_input + self.total_output,
            "call_count": self.call_count
        }