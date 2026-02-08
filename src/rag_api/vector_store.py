"""
Azure AI Search Vector Store
=============================
Production vector database using Azure AI Search for semantic retrieval.

AI Learning Notes:
------------------

## Why Azure AI Search for RAG?

1. **Hybrid Search**: Combines vector similarity + keyword (BM25) search
   - Vector: Semantic meaning ("car" finds "automobile")
   - Keyword: Exact matches (product codes, names)
   - Hybrid: Best of both worlds

2. **Enterprise Ready**: 
   - SLA-backed availability
   - Built-in security (Azure AD, RBAC)
   - Scales to billions of documents

3. **Integrated with Azure OpenAI**:
   - Same Azure subscription
   - Low latency in same region

## Search Score Explained:
- @search.score: BM25 relevance (keyword)
- @search.rerankerScore: Semantic reranker score
- Vector score: Cosine similarity

## Index Schema Design:
- id: Unique document identifier
- content: The actual text
- content_vector: Embedding of the content
- metadata: Title, source, timestamps
- Use filterable fields for scoped search
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SearchableField,
    SimpleField,
)
from azure.search.documents.models import VectorizedQuery

from src.common import get_settings, get_logger
from .embeddings import get_embedding_client

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class SearchResult:
    """A single search result with metadata."""
    id: str
    content: str
    score: float
    title: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class VectorStore:
    """
    Azure AI Search vector store for RAG retrieval.
    
    Usage:
        store = VectorStore()
        
        # Index documents
        await store.index_documents([
            {"id": "1", "content": "Azure is a cloud platform", "title": "Azure Intro"}
        ])
        
        # Search
        results = await store.search("What is cloud computing?")
        for r in results:
            print(f"{r.title}: {r.content[:100]}...")
    """
    
    def __init__(self):
        credential = AzureKeyCredential(settings.azure_search_api_key)
        
        self.search_client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index_name,
            credential=credential,
        )
        
        self.index_client = SearchIndexClient(
            endpoint=settings.azure_search_endpoint,
            credential=credential,
        )
        
        self.embedding_client = get_embedding_client()
    
    async def create_index_if_not_exists(self) -> None:
        """
        Create the search index with vector search capabilities.
        
        Index Schema:
        - id: Unique identifier (key)
        - content: Searchable text content
        - content_vector: Vector embedding for semantic search
        - title: Document title
        - source: Source file/URL
        - chunk_index: Position in original document
        - created_at: Timestamp
        """
        index_name = settings.azure_search_index_name
        
        # Check if index exists
        try:
            self.index_client.get_index(index_name)
            logger.info("index_exists", index_name=index_name)
            return
        except Exception:
            pass  # Index doesn't exist, create it
        
        # Define vector search configuration
        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="hnsw-config",
                    # HNSW parameters affect search quality vs speed
                    # m: connections per node (higher = better recall, slower)
                    # efConstruction: index build quality
                    # efSearch: search quality
                )
            ],
            profiles=[
                VectorSearchProfile(
                    name="vector-profile",
                    algorithm_configuration_name="hnsw-config",
                )
            ],
        )
        
        # Define fields
        fields = [
            SimpleField(
                name="id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SearchableField(
                name="content",
                type=SearchFieldDataType.String,
                searchable=True,
            ),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=settings.embedding_dimensions,
                vector_search_profile_name="vector-profile",
            ),
            SearchableField(
                name="title",
                type=SearchFieldDataType.String,
                searchable=True,
                filterable=True,
            ),
            SimpleField(
                name="source",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="chunk_index",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
            ),
            SimpleField(
                name="created_at",
                type=SearchFieldDataType.DateTimeOffset,
                filterable=True,
                sortable=True,
            ),
        ]
        
        index = SearchIndex(
            name=index_name,
            fields=fields,
            vector_search=vector_search,
        )
        
        self.index_client.create_index(index)
        logger.info("index_created", index_name=index_name)
    
    async def index_documents(
        self, 
        documents: List[Dict[str, Any]],
        generate_embeddings: bool = True,
    ) -> Dict[str, int]:
        """
        Index documents into Azure AI Search.
        
        Args:
            documents: List of documents with 'id', 'content', and optional metadata
            generate_embeddings: Whether to generate embeddings (set False if pre-computed)
            
        Returns:
            Stats about indexed documents
        """
        if not documents:
            return {"indexed": 0, "failed": 0}
        
        # Generate embeddings if needed
        if generate_embeddings:
            contents = [doc["content"] for doc in documents]
            embeddings = await self.embedding_client.embed_batch(contents)
            
            for doc, embedding in zip(documents, embeddings):
                doc["content_vector"] = embedding
        
        # Upload to Azure AI Search
        result = self.search_client.upload_documents(documents)
        
        succeeded = sum(1 for r in result if r.succeeded)
        failed = len(result) - succeeded
        
        logger.info(
            "documents_indexed",
            total=len(documents),
            succeeded=succeeded,
            failed=failed,
        )
        
        return {"indexed": succeeded, "failed": failed}
    
    async def search(
        self,
        query: str,
        top_k: int = None,
        filter_expression: Optional[str] = None,
        use_hybrid: bool = True,
    ) -> List[SearchResult]:
        """
        Search for relevant documents using vector similarity.
        
        Args:
            query: Natural language query
            top_k: Number of results to return
            filter_expression: OData filter (e.g., "source eq 'manual.pdf'")
            use_hybrid: Use both vector and keyword search
            
        Returns:
            List of SearchResult objects ranked by relevance
        """
        top_k = top_k or settings.top_k_results
        
        # Generate query embedding
        query_vector = await self.embedding_client.embed_text(query)
        
        # Create vector query
        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )
        
        # Execute search
        search_params = {
            "vector_queries": [vector_query],
            "top": top_k,
            "select": ["id", "content", "title", "source", "chunk_index"],
        }
        
        if use_hybrid:
            # Hybrid search: vector + text
            search_params["search_text"] = query
        
        if filter_expression:
            search_params["filter"] = filter_expression
        
        results = self.search_client.search(**search_params)
        
        search_results = []
        for result in results:
            # Apply similarity threshold
            score = result.get("@search.score", 0)
            
            search_results.append(SearchResult(
                id=result["id"],
                content=result["content"],
                score=score,
                title=result.get("title"),
                source=result.get("source"),
                metadata={
                    "chunk_index": result.get("chunk_index"),
                }
            ))
        
        logger.info(
            "search_completed",
            query_length=len(query),
            results_count=len(search_results),
            top_score=search_results[0].score if search_results else 0,
        )
        
        return search_results
    
    async def delete_documents(self, ids: List[str]) -> int:
        """Delete documents by ID."""
        documents = [{"id": doc_id} for doc_id in ids]
        result = self.search_client.delete_documents(documents)
        deleted = sum(1 for r in result if r.succeeded)
        logger.info("documents_deleted", count=deleted)
        return deleted


# Singleton instance
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
