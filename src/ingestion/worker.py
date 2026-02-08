"""
Ingestion Worker - Document Processing Pipeline
================================================
Watches Azure Blob Storage for new documents, processes them
(chunking + embedding), and indexes them into Azure AI Search.

AI Learning Notes:
------------------
## Document Ingestion Pipeline:
1. Watch blob storage for new/updated documents
2. Extract text (PDF, DOCX, TXT, MD)
3. Chunk text with overlap for context preservation
4. Generate embeddings via Azure OpenAI
5. Index chunks + vectors into Azure AI Search

## Chunking Strategies:
- Fixed-size chunks: Simple, predictable (this implementation)
- Semantic chunking: Split by meaning boundaries
- Recursive character splitting: Balance size and semantics

## Why Overlap?
Overlap ensures context isn't lost at chunk boundaries.
Example: A sentence split across two chunks remains searchable
because part of it appears in both chunks.
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Optional

from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.storage.blob._models import BlobProperties

from src.common import get_settings, get_logger
from src.rag_api.embeddings import EmbeddingClient, get_embedding_client
from src.rag_api.vector_store import VectorStore, get_vector_store

logger = get_logger(__name__)
settings = get_settings()


class DocumentChunker:
    """Split documents into overlapping chunks for RAG."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str, doc_id: str, source: str) -> List[Dict]:
        """Split text into overlapping chunks with metadata."""
        if not text or not text.strip():
            return []

        chunks = []
        # Clean text
        text = text.strip()
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence-ending punctuation near the boundary
                for sep in ['. ', '.\n', '! ', '? ', '\n\n']:
                    last_sep = text.rfind(sep, start + self.chunk_size // 2, end + 100)
                    if last_sep != -1:
                        end = last_sep + len(sep)
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_id = f"{doc_id}_chunk_{chunk_index}"
                chunks.append({
                    "id": hashlib.md5(chunk_id.encode()).hexdigest(),
                    "content": chunk_text,
                    "title": f"{source} - Part {chunk_index + 1}",
                    "source": source,
                    "metadata": json.dumps({
                        "doc_id": doc_id,
                        "chunk_index": chunk_index,
                        "char_start": start,
                        "char_end": end,
                        "chunk_size": len(chunk_text),
                    }),
                })
                chunk_index += 1

            # Move forward by chunk_size - overlap
            start = start + self.chunk_size - self.chunk_overlap
            if start >= len(text):
                break

        logger.info(
            "Chunked document",
            doc_id=doc_id,
            total_chars=len(text),
            num_chunks=len(chunks),
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
        )
        return chunks


class IngestionWorker:
    """
    Watches Azure Blob Storage and ingests new documents into AI Search.
    
    Architecture:
    ┌──────────────┐     ┌────────────┐     ┌──────────────┐     ┌──────────────┐
    │  Blob Storage │ ──▶ │  Extract   │ ──▶ │   Chunk +    │ ──▶ │  AI Search   │
    │  (documents)  │     │   Text     │     │   Embed      │     │  (vectors)   │
    └──────────────┘     └────────────┘     └──────────────┘     └──────────────┘
    """

    def __init__(self):
        self.chunker = DocumentChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        self.vector_store: Optional[VectorStore] = None
        self.embedding_service: Optional[EmbeddingClient] = None
        self.blob_client: Optional[ContainerClient] = None
        self.processed_blobs: set = set()  # Track what we've processed
        self.poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

    async def initialize(self):
        """Initialize connections to Azure services."""
        logger.info("Initializing Ingestion Worker...")

        # Vector store
        self.vector_store = get_vector_store()
        await self.vector_store.create_index_if_not_exists()

        # Embedding service
        self.embedding_service = get_embedding_client()

        # Blob storage
        if settings.azure_storage_connection_string:
            self.blob_client = BlobServiceClient.from_connection_string(
                settings.azure_storage_connection_string
            ).get_container_client(settings.azure_storage_container)
            # Create container if it doesn't exist
            try:
                self.blob_client.create_container()
                logger.info("Created blob container", container=settings.azure_storage_container)
            except Exception:
                pass  # Container already exists
        else:
            logger.warning("No blob storage connection string - running in manual mode only")

        logger.info("Ingestion Worker initialized successfully")

    def extract_text(self, blob_name: str, content: bytes) -> str:
        """Extract text from document bytes based on file type."""
        ext = blob_name.lower().rsplit(".", 1)[-1] if "." in blob_name else "txt"

        if ext in ("txt", "md", "csv", "json", "log"):
            return content.decode("utf-8", errors="replace")
        elif ext == "json":
            data = json.loads(content)
            return json.dumps(data, indent=2)
        else:
            # For PDF/DOCX, you'd add pypdf, python-docx etc.
            # Keeping deps minimal for cost-optimized deployment
            logger.warning(f"Unsupported file type: {ext}, treating as text")
            return content.decode("utf-8", errors="replace")

    async def process_blob(self, blob_name: str) -> int:
        """Process a single blob: extract → chunk → embed → index."""
        if not self.blob_client:
            logger.warning("No blob client available")
            return 0

        logger.info("Processing blob", blob_name=blob_name)
        start_time = time.time()

        try:
            # Download blob
            blob_data = self.blob_client.download_blob(blob_name).readall()

            # Extract text
            text = self.extract_text(blob_name, blob_data)
            if not text.strip():
                logger.warning("Empty document", blob_name=blob_name)
                return 0

            # Chunk
            doc_id = hashlib.md5(blob_name.encode()).hexdigest()[:12]
            chunks = self.chunker.chunk_text(text, doc_id=doc_id, source=blob_name)

            if not chunks:
                return 0

            # Index into AI Search (embeddings generated inside vector_store)
            await self.vector_store.index_documents(chunks)

            elapsed = time.time() - start_time
            logger.info(
                "Blob processed successfully",
                blob_name=blob_name,
                chunks=len(chunks),
                elapsed_seconds=round(elapsed, 2),
            )
            return len(chunks)

        except Exception as e:
            logger.error("Failed to process blob", blob_name=blob_name, error=str(e))
            return 0

    async def scan_and_process(self) -> Dict:
        """Scan blob storage for new/updated documents and process them."""
        if not self.blob_client:
            return {"status": "no_blob_client", "processed": 0}

        stats = {"scanned": 0, "new": 0, "chunks_created": 0}

        try:
            blobs = self.blob_client.list_blobs()
            for blob in blobs:
                stats["scanned"] += 1
                blob_key = f"{blob.name}:{blob.last_modified}"

                if blob_key not in self.processed_blobs:
                    chunks = await self.process_blob(blob.name)
                    if chunks > 0:
                        self.processed_blobs.add(blob_key)
                        stats["new"] += 1
                        stats["chunks_created"] += chunks

        except Exception as e:
            logger.error("Scan failed", error=str(e))
            stats["error"] = str(e)

        return stats

    async def run_poll_loop(self):
        """Main poll loop - continuously check for new documents."""
        logger.info(
            "Starting poll loop",
            interval_seconds=self.poll_interval,
        )

        while True:
            try:
                stats = await self.scan_and_process()
                if stats.get("new", 0) > 0:
                    logger.info("Poll cycle complete", **stats)
                else:
                    logger.debug("Poll cycle - no new documents")
            except Exception as e:
                logger.error("Poll loop error", error=str(e))

            await asyncio.sleep(self.poll_interval)


async def main():
    """Entry point for the ingestion worker."""
    worker = IngestionWorker()
    await worker.initialize()

    logger.info(
        "=== Ingestion Worker Started ===",
        poll_interval=worker.poll_interval,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    await worker.run_poll_loop()


if __name__ == "__main__":
    asyncio.run(main())
