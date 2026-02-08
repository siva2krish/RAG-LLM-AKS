"""
Azure OpenAI LLM Client
========================
Production-ready wrapper for Azure OpenAI with:
- Streaming support for real-time responses
- Token counting and cost tracking
- Retry logic with exponential backoff
- Structured output support

AI Learning Notes:
------------------
1. TOKENS: LLMs process text as tokens (~4 chars = 1 token)
   - Input tokens (your prompt) + Output tokens (response)
   - GPT-4o: ~$5/1M input, ~$15/1M output tokens
   
2. TEMPERATURE: Controls randomness (0=deterministic, 1=creative)
   - For RAG: Use 0-0.3 for factual responses
   
3. MAX_TOKENS: Limits response length, not context window
   - GPT-4o context: 128K tokens
"""

from typing import AsyncGenerator, Optional, List, Dict, Any
from dataclasses import dataclass
import tiktoken
from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common import get_settings, get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class LLMResponse:
    """Structured LLM response with metadata."""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    finish_reason: str
    
    @property
    def estimated_cost_usd(self) -> float:
        """Estimate cost based on GPT-4o pricing."""
        # Approximate pricing - adjust based on actual Azure pricing
        input_cost = self.input_tokens * 0.000005   # $5/1M tokens
        output_cost = self.output_tokens * 0.000015  # $15/1M tokens
        return input_cost + output_cost


class AzureOpenAIClient:
    """
    Production Azure OpenAI client with best practices.
    
    Usage:
        client = AzureOpenAIClient()
        response = await client.chat("What is RAG?")
        print(f"Answer: {response.content}")
        print(f"Cost: ${response.estimated_cost_usd:.4f}")
    """
    
    def __init__(self):
        self.client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment_name = settings.azure_openai_deployment_name
        
        # Token encoder for counting
        try:
            self.encoder = tiktoken.encoding_for_model("gpt-4o")
        except KeyError:
            self.encoder = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text. Essential for managing context windows."""
        return len(self.encoder.encode(text))
    
    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count tokens in a message list (accounts for message formatting overhead)."""
        tokens = 0
        for message in messages:
            tokens += 4  # Message formatting overhead
            tokens += self.count_tokens(message.get("content", ""))
            tokens += self.count_tokens(message.get("role", ""))
        tokens += 2  # Conversation priming
        return tokens
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        context_documents: Optional[List[str]] = None,
    ) -> LLMResponse:
        """
        Send a chat completion request.
        
        Args:
            user_message: The user's question/prompt
            system_prompt: System instructions (persona, rules)
            temperature: Randomness (0-1). Lower = more deterministic
            max_tokens: Maximum response length
            context_documents: Retrieved documents for RAG
            
        Returns:
            LLMResponse with content and usage metadata
        """
        messages = []
        
        # Build system prompt with RAG context
        if system_prompt or context_documents:
            system_content = system_prompt or "You are a helpful AI assistant."
            
            if context_documents:
                # Inject retrieved context into system prompt
                context_str = "\n\n---\n\n".join(context_documents)
                system_content += f"""

## Retrieved Context
Use the following documents to answer the user's question. 
If the answer is not in the context, say so clearly.

{context_str}
"""
            messages.append({"role": "system", "content": system_content})
        
        messages.append({"role": "user", "content": user_message})
        
        # Log token count before request
        input_tokens = self.count_messages_tokens(messages)
        logger.info("llm_request", input_tokens=input_tokens, model=self.deployment_name)
        
        response = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        result = LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            finish_reason=response.choices[0].finish_reason,
        )
        
        logger.info(
            "llm_response",
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            cost_usd=result.estimated_cost_usd,
        )
        
        return result
    
    async def chat_stream(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        context_documents: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion for real-time UI updates.
        
        Streaming is essential for good UX - users see responses immediately
        rather than waiting for full completion.
        
        Usage:
            async for chunk in client.chat_stream("Hello"):
                print(chunk, end="", flush=True)
        """
        messages = []
        
        if system_prompt or context_documents:
            system_content = system_prompt or "You are a helpful AI assistant."
            
            if context_documents:
                context_str = "\n\n---\n\n".join(context_documents)
                system_content += f"""

## Retrieved Context
{context_str}
"""
            messages.append({"role": "system", "content": system_content})
        
        messages.append({"role": "user", "content": user_message})
        
        stream = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# Singleton instance
_llm_client: Optional[AzureOpenAIClient] = None


def get_llm_client() -> AzureOpenAIClient:
    """Get or create LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = AzureOpenAIClient()
    return _llm_client
