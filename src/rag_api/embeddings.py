"""
Azure OpenAI Embeddings Client
===============================
Converts text to vector embeddings for semantic search.

AI Learning Notes:
------------------

## What are Embeddings?
Embeddings are numerical representations of text where semantically similar 
content has similar vector values. This enables:
- Semantic search (find similar meaning, not just keywords)
- Document clustering
- Recommendation systems

## How it Works:
1. Text → Tokenize → Neural Network → Fixed-size vector
2. "Hello world" → [0.023, -0.041, 0.089, ...] (1536 or 3072 dimensions)

## Vector Similarity:
- Cosine Similarity: cos(θ) = A·B / (||A|| × ||B||)
- Range: -1 to 1 (1 = identical, 0 = unrelated, -1 = opposite)

## Model Comparison:
| Model                    | Dimensions | Best For           |
|--------------------------|------------|-------------------|
| text-embedding-3-small   | 1536       | Cost-effective    |
| text-embedding-3-large   | 3072       | Higher accuracy   |
| text-embedding-ada-002   | 1536       | Legacy            |

## Chunking Strategy:
Text must be chunked before embedding because:
1. Models have token limits (~8K for embedding models)
2. Smaller chunks = more precise retrieval
3. But too small = loss of context

Recommended: 500-1000 tokens with 100-200 overlap
"""

from typing import List, Optional
import numpy as np
from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common import get_settings, get_logger

logger = get_logger(__name__)
settings = get_settings()


class EmbeddingClient:
    """
    Azure OpenAI Embeddings with batching support.
    
    Usage:
        client = EmbeddingClient()
        
        # Single text
        vector = await client.embed_text("What is machine learning?")
        
        # Batch processing (more efficient)
        vectors = await client.embed_batch(["text1", "text2", "text3"])
    """
    
    def __init__(self):
        self.client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment_name = settings.azure_openai_embedding_deployment
        self.dimensions = settings.embedding_dimensions
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if not text.strip():
            raise ValueError("Cannot embed empty text")
        
        response = await self.client.embeddings.create(
            model=self.deployment_name,
            input=text,
        )
        
        embedding = response.data[0].embedding
        
        logger.debug(
            "embedding_generated",
            text_length=len(text),
            dimensions=len(embedding),
            tokens=response.usage.total_tokens,
        )
        
        return embedding
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_batch(
        self, 
        texts: List[str], 
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Batching is important because:
        1. Reduces API calls (cost and latency)
        2. Azure has rate limits - batching helps stay within
        3. More efficient network utilization
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call (max ~100)
            
        Returns:
            List of embedding vectors in same order as input
        """
        if not texts:
            return []
        
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # Filter empty strings
            batch = [t for t in batch if t.strip()]
            
            if not batch:
                continue
            
            response = await self.client.embeddings.create(
                model=self.deployment_name,
                input=batch,
            )
            
            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            batch_embeddings = [item.embedding for item in sorted_data]
            all_embeddings.extend(batch_embeddings)
            
            logger.info(
                "batch_embeddings_generated",
                batch_size=len(batch),
                total_tokens=response.usage.total_tokens,
            )
        
        return all_embeddings
    
    def cosine_similarity(
        self, 
        vec1: List[float], 
        vec2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        This is the core of semantic search:
        - 1.0 = identical meaning
        - 0.0 = unrelated
        - -1.0 = opposite meaning (rare in practice)
        
        Args:
            vec1: First embedding vector
            vec2: Second embedding vector
            
        Returns:
            Similarity score between -1 and 1
        """
        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# Singleton instance
_embedding_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """Get or create embedding client instance."""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
