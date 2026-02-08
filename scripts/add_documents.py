#!/usr/bin/env python3
"""
Add Custom Documents to Azure AI Search
========================================

Usage:
    # From inside the RAG pod (already has credentials):
    kubectl exec -it deploy/rag-system -n rag-system -- python /app/scripts/add_documents.py

    # Or run locally with environment variables set
"""

import asyncio
from typing import List, Dict

# Sample documents - EDIT THESE with your content
CUSTOM_DOCUMENTS = [
    {
        "id": "custom-001",
        "title": "My Custom Document",
        "content": """
        Add your custom content here. This can be:
        - Technical documentation
        - Company policies
        - Product information
        - FAQ content
        - Any text you want to search
        """,
        "source": "custom-docs",
    },
    {
        "id": "custom-002", 
        "title": "Another Document",
        "content": """
        More content here. The RAG system will:
        1. Generate embeddings for this text
        2. Store in Azure AI Search
        3. Retrieve when users ask related questions
        """,
        "source": "custom-docs",
    },
    # Add more documents here...
]


async def add_documents(documents: List[Dict]):
    """Add documents to the search index with embeddings."""
    from src.rag_api.vector_store import VectorStore
    
    store = VectorStore()
    
    # Ensure index exists
    await store.create_index_if_not_exists()
    
    # Index documents (will generate embeddings automatically)
    result = await store.index_documents(documents, generate_embeddings=True)
    
    print(f"✅ Indexed {result['indexed']} documents")
    if result['failed'] > 0:
        print(f"❌ Failed: {result['failed']}")
    
    return result


async def list_all_documents():
    """List all documents in the index."""
    from src.rag_api.vector_store import VectorStore
    
    store = VectorStore()
    results = list(store.search_client.search('*', top=100, select=['id', 'title', 'source']))
    
    print(f"\n📚 Total documents in index: {len(results)}")
    for doc in results:
        print(f"  - {doc['id']}: {doc.get('title', 'N/A')} ({doc.get('source', 'N/A')})")


async def delete_document(doc_id: str):
    """Delete a specific document."""
    from src.rag_api.vector_store import VectorStore
    
    store = VectorStore()
    store.search_client.delete_documents([{"id": doc_id}])
    print(f"🗑️ Deleted document: {doc_id}")


async def main():
    print("🚀 Adding custom documents to Azure AI Search...\n")
    
    # Add the documents
    await add_documents(CUSTOM_DOCUMENTS)
    
    # List all documents
    await list_all_documents()


if __name__ == "__main__":
    asyncio.run(main())
