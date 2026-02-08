#!/usr/bin/env python3
"""
Initialize Azure AI Search Index with Sample Documents
======================================================
This script creates the search index and uploads sample documents for testing.

Usage:
    python scripts/init_search_index.py

The script will:
1. Create the search index with vector configuration
2. Generate embeddings for sample documents
3. Upload documents to the index
"""

import asyncio
import os
from datetime import datetime, timezone
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
from openai import AzureOpenAI

# Load from environment
AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
EMBEDDING_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "rag-documents")

# Embedding dimensions: text-embedding-3-small = 1536, text-embedding-3-large = 3072
EMBEDDING_DIMENSIONS = 1536 if "small" in EMBEDDING_DEPLOYMENT else 3072

# Sample documents for RAG testing
SAMPLE_DOCUMENTS = [
    {
        "id": "doc-001",
        "title": "Introduction to Kubernetes",
        "content": """Kubernetes (K8s) is an open-source container orchestration platform that automates 
the deployment, scaling, and management of containerized applications. Originally developed by Google, 
it is now maintained by the Cloud Native Computing Foundation (CNCF). Kubernetes groups containers 
into logical units called Pods for easy management and discovery. Key components include: 
- Control Plane: API server, scheduler, controller manager, etcd
- Worker Nodes: kubelet, kube-proxy, container runtime
- Objects: Pods, Deployments, Services, ConfigMaps, Secrets
Kubernetes provides declarative configuration and automation, making it ideal for microservices architectures.""",
        "source": "kubernetes-docs",
    },
    {
        "id": "doc-002", 
        "title": "Azure Kubernetes Service (AKS) Overview",
        "content": """Azure Kubernetes Service (AKS) is Microsoft's managed Kubernetes offering that simplifies 
deploying and managing containerized applications. With AKS, Azure handles critical tasks like health monitoring 
and maintenance. Key features include:
- Managed control plane (free tier available)
- Integration with Azure Active Directory for RBAC
- Azure CNI and Kubenet networking options
- Virtual Node support for serverless scaling
- Azure Monitor integration for observability
- KEDA for event-driven autoscaling
AKS supports both Linux and Windows node pools, making it versatile for various workloads.""",
        "source": "azure-aks-docs",
    },
    {
        "id": "doc-003",
        "title": "RAG (Retrieval-Augmented Generation) Explained",
        "content": """Retrieval-Augmented Generation (RAG) is an AI architecture pattern that enhances 
Large Language Models (LLMs) by retrieving relevant information from external knowledge bases before 
generating responses. The RAG pipeline consists of:
1. Document Ingestion: Chunking, embedding, and indexing documents
2. Retrieval: Finding relevant chunks using vector similarity search
3. Augmentation: Adding retrieved context to the LLM prompt
4. Generation: LLM generates response using the augmented context
Benefits of RAG include: reduced hallucinations, up-to-date information, source attribution, 
and domain-specific knowledge without fine-tuning. Common vector databases include Azure AI Search, 
Pinecone, Weaviate, and Chroma.""",
        "source": "ai-patterns",
    },
    {
        "id": "doc-004",
        "title": "Azure OpenAI Service",
        "content": """Azure OpenAI Service provides REST API access to OpenAI's powerful language models 
including GPT-4, GPT-4o, GPT-3.5-Turbo, and embedding models. Key differences from OpenAI API:
- Enterprise security with Azure AD authentication
- Private networking via Private Endpoints
- Regional deployment for data residency compliance
- Content filtering and responsible AI features
- SLA-backed availability
Models available: GPT-4o (latest multimodal), GPT-4o-mini (cost-effective), text-embedding-3-small, 
text-embedding-3-large. Pricing is per 1000 tokens, with input tokens cheaper than output tokens.""",
        "source": "azure-openai-docs",
    },
    {
        "id": "doc-005",
        "title": "Vector Search and Embeddings",
        "content": """Vector search enables semantic similarity search by converting text into high-dimensional 
vectors (embeddings) that capture meaning. Key concepts:
- Embeddings: Dense vector representations of text (1536 or 3072 dimensions for OpenAI models)
- Cosine Similarity: Measures angle between vectors (1.0 = identical, 0 = orthogonal)
- HNSW (Hierarchical Navigable Small World): Efficient approximate nearest neighbor algorithm
- Hybrid Search: Combines vector similarity with keyword (BM25) search for better results
Azure AI Search supports vector search with configurable algorithms. Best practices:
- Chunk documents appropriately (500-1000 tokens)
- Use overlapping chunks to preserve context
- Consider hybrid search for production workloads""",
        "source": "vector-search-guide",
    },
    {
        "id": "doc-006",
        "title": "KEDA - Kubernetes Event-Driven Autoscaling",
        "content": """KEDA (Kubernetes Event-Driven Autoscaling) extends Kubernetes with event-driven 
autoscaling capabilities. Unlike HPA which scales on CPU/memory, KEDA can scale based on:
- Message queue length (Azure Service Bus, RabbitMQ, Kafka)
- HTTP request rate (using Prometheus metrics)
- Custom metrics from any source
- Cron schedules
KEDA components include: Operator, Metrics Server, and Admission Webhooks. Key resources:
- ScaledObject: Defines scaling behavior for deployments
- ScaledJob: Scales Jobs based on event count
KEDA can scale to zero pods when there are no events, saving costs for bursty workloads.""",
        "source": "keda-docs",
    },
    {
        "id": "doc-007",
        "title": "Helm - Kubernetes Package Manager",
        "content": """Helm is the package manager for Kubernetes, simplifying deployment of complex applications. 
Key concepts:
- Charts: Packages containing Kubernetes resource templates
- Values: Configuration that customizes chart deployment
- Releases: Instances of charts running in a cluster
- Repositories: Storage for sharing charts
Helm commands:
- helm install: Deploy a chart
- helm upgrade: Update a release
- helm rollback: Revert to previous version
- helm list: View installed releases
Best practices: Use values files for environment-specific config, version your charts, 
implement proper RBAC, and use helm diff to preview changes before applying.""",
        "source": "helm-docs",
    },
    {
        "id": "doc-008",
        "title": "FastAPI for Production APIs",
        "content": """FastAPI is a modern Python web framework for building APIs with automatic OpenAPI 
documentation. Key features:
- Async/await support for high performance
- Automatic request validation using Pydantic
- OpenAPI (Swagger) docs generated automatically
- Dependency injection system
- WebSocket support
Production best practices:
- Use Uvicorn with Gunicorn for process management
- Implement proper health check endpoints (/health, /ready)
- Add structured logging with correlation IDs
- Use middleware for authentication, rate limiting
- Implement graceful shutdown handling
FastAPI is ideal for AI/ML APIs due to its async support and automatic documentation.""",
        "source": "fastapi-guide",
    },
]


def create_index(index_client: SearchIndexClient, index_name: str) -> None:
    """Create the search index with vector configuration."""
    
    # Check if index exists
    try:
        index_client.get_index(index_name)
        print(f"✓ Index '{index_name}' already exists")
        return
    except Exception:
        pass
    
    # Vector search configuration
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-config",
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw-config",
            )
        ],
    )
    
    # Index fields
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String, searchable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="vector-profile",
        ),
        SearchableField(name="title", type=SearchFieldDataType.String, searchable=True, filterable=True),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SimpleField(name="created_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
    ]
    
    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    index_client.create_index(index)
    print(f"✓ Created index '{index_name}'")


def generate_embeddings(openai_client: AzureOpenAI, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for texts using Azure OpenAI."""
    response = openai_client.embeddings.create(
        input=texts,
        model=EMBEDDING_DEPLOYMENT,
    )
    return [item.embedding for item in response.data]


def upload_documents(
    search_client: SearchClient, 
    openai_client: AzureOpenAI,
    documents: list[dict],
) -> None:
    """Upload documents with embeddings to the search index."""
    
    # Generate embeddings
    print(f"Generating embeddings for {len(documents)} documents...")
    contents = [doc["content"] for doc in documents]
    embeddings = generate_embeddings(openai_client, contents)
    
    # Prepare documents with embeddings
    now = datetime.now(timezone.utc)
    docs_to_upload = []
    for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
        docs_to_upload.append({
            "id": doc["id"],
            "content": doc["content"],
            "content_vector": embedding,
            "title": doc["title"],
            "source": doc["source"],
            "chunk_index": i,
            "created_at": now.isoformat(),
        })
    
    # Upload
    result = search_client.upload_documents(docs_to_upload)
    succeeded = sum(1 for r in result if r.succeeded)
    print(f"✓ Uploaded {succeeded}/{len(documents)} documents")


def main():
    # Validate environment
    required_vars = [
        ("AZURE_SEARCH_ENDPOINT", AZURE_SEARCH_ENDPOINT),
        ("AZURE_SEARCH_API_KEY", AZURE_SEARCH_API_KEY),
        ("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT),
        ("AZURE_OPENAI_API_KEY", AZURE_OPENAI_API_KEY),
    ]
    
    missing = [name for name, value in required_vars if not value]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print("\nSet them with:")
        for var in missing:
            print(f"  export {var}=<value>")
        return 1
    
    print(f"\n🔧 Initializing Azure AI Search Index")
    print(f"   Endpoint: {AZURE_SEARCH_ENDPOINT}")
    print(f"   Index: {INDEX_NAME}")
    print(f"   Embedding Model: {EMBEDDING_DEPLOYMENT}")
    print(f"   Dimensions: {EMBEDDING_DIMENSIONS}\n")
    
    # Initialize clients
    credential = AzureKeyCredential(AZURE_SEARCH_API_KEY)
    index_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=credential)
    search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=INDEX_NAME, credential=credential)
    openai_client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version="2024-02-01",
    )
    
    # Create index
    create_index(index_client, INDEX_NAME)
    
    # Upload sample documents
    upload_documents(search_client, openai_client, SAMPLE_DOCUMENTS)
    
    print(f"\n✅ Search index ready! You can now use /api/v1/query endpoint")
    print(f"\nTest queries:")
    print(f'  - "What is Kubernetes?"')
    print(f'  - "Explain RAG architecture"')
    print(f'  - "How does KEDA work?"')
    
    return 0


if __name__ == "__main__":
    exit(main())
