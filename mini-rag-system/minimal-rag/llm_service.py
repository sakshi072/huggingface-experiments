"""
LLM Service using HuggingFace Serverless API
Phase 2: Using OpenAI-compatible client with router endpoint

This actually works! Uses: https://router.huggingface.co
"""

import os
import time
from typing import List, Dict
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMService:
    """
    Service to generate answers using HuggingFace Serverless API.
    
    Uses OpenAI-compatible client pointing to HuggingFace router.
    This is the NEW recommended approach!
    """
    
    # Working models on router endpoint (chat-compatible)
    MODELS = {
        "llama": "meta-llama/Llama-3.2-3B-Instruct",
        "qwen": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "phi": "google/gemma-2-2b-it",
        "mistral": "mistralai/Mistral-Nemo-Instruct-2407",
    }
    
    def __init__(self, model_name: str = "llama"):
        """
        Initialize LLM service with HuggingFace router.
        
        Args:
            model_name: Model to use (llama, qwen, phi, mistral)
        """
        self.api_key = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN")
        if not self.api_key:
            raise ValueError(
                "HUGGINGFACE_API_KEY not found! "
                "Please set it in .env file."
            )
        
        self.model_id = self.MODELS.get(model_name, self.MODELS["llama"])
        
        print(f"🤖 Initializing HuggingFace Serverless API")
        print(f"   Model: {self.model_id}")
        print(f"   Endpoint: https://router.huggingface.co")
        
        try:
            # Use OpenAI client pointed at HuggingFace router
            self.client = OpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=self.api_key
            )
            print(f"   ✅ Client initialized!")
            
        except Exception as e:
            print(f"   ❌ Error initializing client: {e}")
            raise
    
    def _build_messages(
        self,
        query: str,
        context_chunks: List[Dict]
    ) -> List[Dict[str, str]]:
        """
        Build chat messages for the LLM.
        """
        # Format context
        context_parts = []
        for i, chunk in enumerate(context_chunks[:5], 1):
            text = chunk.get('chunk', '')
            context_parts.append(f"{text}")
        
        context = "\n\n".join(context_parts)
        
        # Build messages
        messages = [
            {
                "role": "system",
                "content": """You are a helpful AI assistant. You will be given context information and a question. 
Your task is to answer the question using ONLY the information provided in the context.
Read the context carefully and extract relevant information to answer the question.
If the answer is in the context, provide it. If not, say you cannot find the answer."""
            },
            {
                "role": "user",
                "content": f"""Here is the context information:

{context}

Now answer this question based on the context above: {query}

Provide a clear, direct answer using the information from the context."""
            }
        ]
        
        return messages
    
    def generate(
        self,
        query: str,
        context_chunks: List[Dict],
        max_tokens: int = 50,
        temperature: float = 0.7,
        retry_count: int = 3
    ) -> str:
        """
        Generate answer using HuggingFace LLM.
        
        Args:
            query: User question
            context_chunks: Retrieved context
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            retry_count: Number of retries
            
        Returns:
            Generated answer
        """
        if not context_chunks:
            return "I cannot answer this question as no relevant context was found."
        
        print(f"   🤖 Generating answer...")
        
        # Build messages
        messages = self._build_messages(query, context_chunks)
        
        # Try with retries
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                
                # Call chat completion API (OpenAI-compatible)
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False
                )
                
                elapsed = time.time() - start_time
                
                # Extract answer
                answer = response.choices[0].message.content
                
                print(f"   ✅ Answer generated in {elapsed:.2f}s")
                return answer.strip()
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Handle model loading
                if "loading" in error_msg or "503" in error_msg:
                    wait_time = 20 * (attempt + 1)
                    print(f"   ⏳ Model loading... waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                
                # Handle rate limiting
                if "429" in error_msg or "rate limit" in error_msg:
                    wait_time = 30 * (attempt + 1)
                    print(f"   ⏳ Rate limited... waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                
                print(f"   ❌ Error (attempt {attempt + 1}/{retry_count}): {e}")
                
                if attempt < retry_count - 1:
                    wait_time = 10 * (attempt + 1)
                    print(f"   ⏳ Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # Fallback
                    return f"Error: {str(e)}. Context: {context_chunks[0]['text'][:200]}..."
        
        return "Failed to generate answer after multiple attempts."
    
    def test_connection(self) -> bool:
        """
        Test if the API connection works.
        
        Returns:
            True if successful
        """
        print("🧪 Testing HuggingFace Serverless API...")
        
        try:
            # Simple test
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "user", "content": "Say 'Hello!' and nothing else."}
                ],
                max_tokens=10,
                temperature=0.1
            )
            
            answer = response.choices[0].message.content
            
            print("   ✅ Connection successful!")
            print(f"   ✅ Test response: {answer}")
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "loading" in error_msg or "503" in error_msg:
                print("   ⏳ Model is loading (first time can take 30-60s)...")
                print("   💡 Try again in a minute!")
                return False
            
            if "401" in error_msg or "unauthorized" in error_msg:
                print("   ❌ Invalid API key!")
                return False
            
            print(f"   ❌ Connection failed: {e}")
            return False


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("HuggingFace Serverless API - Test")
    print("=" * 60)
    
    # Initialize
    try:
        llm = LLMService(model_name="llama")  # Llama 3.2 works well
    except ValueError as e:
        print(f"\n❌ {e}")
        print("\nCreate a .env file with:")
        print("HUGGINGFACE_API_KEY=hf_your_token_here")
        print("\nGet token at: https://huggingface.co/settings/tokens")
        exit(1)
    
    # Test connection
    print()
    if not llm.test_connection():
        print("\n⚠️  API not ready. Wait 30-60s and try again.")
        exit(0)
    
    # Test generation
    print("\n" + "=" * 60)
    print("Testing Answer Generation")
    print("=" * 60)
    
    sample_chunks = [
        {
            "text": "Machine learning is a subset of artificial intelligence that enables systems to learn from data.",
            "source": "ml_basics.txt"
        },
        {
            "text": "Deep learning uses neural networks with multiple layers to process complex patterns.",
            "source": "ml_basics.txt"
        }
    ]
    
    question = "What is machine learning?"
    
    print(f"\nQuestion: {question}\n")
    answer = llm.generate(question, sample_chunks, max_tokens=100)
    
    print("\n" + "=" * 60)
    print("Generated Answer:")
    print("=" * 60)
    print(answer)
    print("\n" + "=" * 60)
    print("✅ Test complete!")
    print("\n💡 Available models:")
    print("   llama   - Fast, recommended (default)")
    print("   phi     - Very fast, good quality")
    print("   qwen    - Code-focused, excellent")
    print("   mistral - Nemo model, high quality")