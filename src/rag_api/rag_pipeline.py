"""
RAG Pipeline - The Heart of the System
=======================================
Orchestrates retrieval and generation for question answering.

AI Learning Notes:
------------------

## RAG (Retrieval-Augmented Generation) Flow:

1. **User Query** → "How do I deploy to Kubernetes?"

2. **Retrieval** (this module)
   - Convert query to embedding
   - Search vector store for similar documents
   - Retrieve top-k relevant chunks

3. **Augmentation**
   - Format retrieved documents as context
   - Build prompt: System + Context + User Question

4. **Generation**
   - Send augmented prompt to LLM
   - LLM generates response grounded in retrieved context

## Why RAG vs Fine-Tuning?

| Aspect        | RAG                      | Fine-Tuning              |
|---------------|--------------------------|--------------------------|
| Data updates  | Easy (re-index)          | Hard (re-train)          |
| Cost          | Lower (retrieval only)   | Higher (GPU training)    |
| Accuracy      | Cites sources            | May hallucinate          |
| Best for      | Knowledge bases, docs    | Style, format, domain    |

## Retrieval Quality Metrics:

- **Recall@k**: % of relevant docs in top-k results
- **MRR**: Mean Reciprocal Rank of first relevant result
- **NDCG**: Normalized Discounted Cumulative Gain

## Prompt Engineering for RAG:

Key principles:
1. Clear instructions about using context
2. Explicit handling of "not in context" cases
3. Citation of sources when possible
4. Formatting guidelines for responses
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import hashlib

from src.common import get_settings, get_logger
from .llm_client import get_llm_client, LLMResponse
from .vector_store import get_vector_store, SearchResult
from .cache import get_cache

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class RAGResponse:
    """Complete RAG response with sources and metadata."""
    answer: str
    sources: List[Dict[str, Any]]
    query: str
    llm_response: LLMResponse
    retrieved_count: int
    from_cache: bool
    latency_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "answer": self.answer,
            "sources": self.sources,
            "metadata": {
                "query": self.query,
                "retrieved_documents": self.retrieved_count,
                "input_tokens": self.llm_response.input_tokens,
                "output_tokens": self.llm_response.output_tokens,
                "total_tokens": self.llm_response.total_tokens,
                "estimated_cost_usd": self.llm_response.estimated_cost_usd,
                "from_cache": self.from_cache,
                "latency_ms": self.latency_ms,
            }
        }


# RAG System Prompt - Critical for quality
RAG_SYSTEM_PROMPT = """You are a knowledgeable AI assistant that answers questions based on provided documentation.

## Instructions:
1. Answer ONLY based on the retrieved context provided below
2. If the context doesn't contain enough information, say: "I don't have enough information in the documentation to answer this question."
3. When citing information, reference the source document
4. Be concise but thorough
5. Use bullet points or numbered lists for complex answers
6. If asked about code, provide examples when available in context

## Response Format:
- Start with a direct answer
- Provide supporting details
- Cite sources in [brackets]
- End with relevant caveats if any

## Important:
- Never make up information not in the context
- If partially relevant info exists, acknowledge the limitation
- Maintain a helpful, professional tone
"""


class RAGPipeline:
    """
    Main RAG orchestration pipeline.
    
    Usage:
        rag = RAGPipeline()
        response = await rag.query("How do I configure Azure OpenAI?")
        print(response.answer)
        print(f"Sources: {response.sources}")
    """
    
    def __init__(self):
        self.llm = get_llm_client()
        self.vector_store = get_vector_store()
        self.cache = get_cache()
    
    def _get_cache_key(self, query: str) -> str:
        """Generate cache key from query."""
        return f"rag:{hashlib.md5(query.lower().strip().encode()).hexdigest()}"
    
    async def query(
        self,
        question: str,
        top_k: int = None,
        filter_expression: Optional[str] = None,
        use_cache: bool = True,
        temperature: float = 0.1,
        custom_system_prompt: Optional[str] = None,
    ) -> RAGResponse:
        """
        Execute RAG pipeline: Retrieve → Augment → Generate.
        
        Args:
            question: User's natural language question
            top_k: Number of documents to retrieve
            filter_expression: Filter to scope search (e.g., by document type)
            use_cache: Whether to use semantic caching
            temperature: LLM temperature (lower = more deterministic)
            custom_system_prompt: Override default system prompt
            
        Returns:
            RAGResponse with answer, sources, and metadata
        """
        import time
        start_time = time.time()
        
        top_k = top_k or settings.top_k_results
        
        # Check cache first
        cache_key = self._get_cache_key(question)
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info("cache_hit", query=question[:50])
                # Return cached dict directly (already in API format)
                # Add from_cache flag to metadata
                cached["metadata"]["from_cache"] = True
                return cached  # Return dict, not RAGResponse
        
        # Step 1: Retrieve relevant documents
        logger.info("rag_retrieve_start", query=question[:100])
        search_results = await self.vector_store.search(
            query=question,
            top_k=top_k,
            filter_expression=filter_expression,
        )
        
        # Filter by similarity threshold
        relevant_results = [
            r for r in search_results 
            if r.score >= settings.similarity_threshold
        ]
        
        if not relevant_results:
            # No relevant context found - still answer but note limitation
            logger.warning("no_relevant_context", query=question[:100])
        
        # Step 2: Format context for LLM
        context_documents = []
        sources = []
        
        for i, result in enumerate(relevant_results):
            # Format each document with source info
            doc_text = f"[Document {i+1}: {result.title or result.source or 'Unknown'}]\n{result.content}"
            context_documents.append(doc_text)
            
            sources.append({
                "id": result.id,
                "title": result.title,
                "source": result.source,
                "score": result.score,
                "excerpt": result.content[:200] + "..." if len(result.content) > 200 else result.content,
            })
        
        # Step 3: Generate answer with LLM
        logger.info("rag_generate_start", context_docs=len(context_documents))
        
        system_prompt = custom_system_prompt or RAG_SYSTEM_PROMPT
        
        llm_response = await self.llm.chat(
            user_message=question,
            system_prompt=system_prompt,
            temperature=temperature,
            context_documents=context_documents,
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        response = RAGResponse(
            answer=llm_response.content,
            sources=sources,
            query=question,
            llm_response=llm_response,
            retrieved_count=len(relevant_results),
            from_cache=False,
            latency_ms=latency_ms,
        )
        
        # Cache the response
        if use_cache:
            await self.cache.set(cache_key, response.to_dict(), ttl_seconds=3600)
        
        logger.info(
            "rag_complete",
            latency_ms=latency_ms,
            tokens=llm_response.total_tokens,
            sources=len(sources),
        )
        
        return response
    
    async def query_stream(
        self,
        question: str,
        top_k: int = None,
        filter_expression: Optional[str] = None,
    ):
        """
        Stream RAG response for real-time UI.
        
        Yields chunks of the answer as they're generated.
        Also yields source documents at the end.
        """
        top_k = top_k or settings.top_k_results
        
        # Retrieve documents
        search_results = await self.vector_store.search(
            query=question,
            top_k=top_k,
            filter_expression=filter_expression,
        )
        
        relevant_results = [
            r for r in search_results 
            if r.score >= settings.similarity_threshold
        ]
        
        # Format context
        context_documents = []
        sources = []
        
        for i, result in enumerate(relevant_results):
            doc_text = f"[Document {i+1}: {result.title or 'Unknown'}]\n{result.content}"
            context_documents.append(doc_text)
            sources.append({
                "title": result.title,
                "source": result.source,
                "score": result.score,
            })
        
        # Stream the response
        async for chunk in self.llm.chat_stream(
            user_message=question,
            system_prompt=RAG_SYSTEM_PROMPT,
            context_documents=context_documents,
        ):
            yield {"type": "content", "data": chunk}
        
        # Send sources at the end
        yield {"type": "sources", "data": sources}


# Singleton instance
_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    """Get or create RAG pipeline instance."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline
