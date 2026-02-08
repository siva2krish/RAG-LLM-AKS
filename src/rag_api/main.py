"""
RAG API - FastAPI Application Entry Point
==========================================
Production-ready API with health checks, observability, and error handling.

AI Learning Notes:
------------------
- Health endpoints critical for Kubernetes liveness/readiness probes
- OpenTelemetry tracing for distributed systems observability
- Structured logging for production debugging
"""

import time
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.common import get_settings, get_logger

logger = get_logger(__name__)
settings = get_settings()


# =============================================================================
# Request/Response Models
# =============================================================================

class QueryRequest(BaseModel):
    """RAG query request model."""
    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    top_k: Optional[int] = Field(default=None, ge=1, le=20, description="Override default top_k")
    include_sources: bool = Field(default=True, description="Include source documents in response")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "How do I deploy my application to Kubernetes?",
                "top_k": 5,
                "include_sources": True
            }
        }


class QueryResponse(BaseModel):
    """RAG query response model."""
    answer: str
    sources: list = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    environment: str
    checks: dict = Field(default_factory=dict)


# =============================================================================
# Application Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    logger.info(
        "Starting RAG API",
        environment=settings.app_env,
        version="1.0.0"
    )
    
    # Initialize connections (lazy loading handles most)
    yield
    
    # Shutdown
    logger.info("Shutting down RAG API")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="RAG + LLM API",
    description="Production RAG system with Azure OpenAI and AI Search",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,  # Disable in prod
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Middleware
# =============================================================================

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add response timing for observability."""
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response


# =============================================================================
# Health Endpoints (Critical for Kubernetes)
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Liveness probe endpoint.
    
    AI Learning Note:
    - Kubernetes uses this to know if the pod is alive
    - If this fails, K8s will restart the pod
    - Keep it simple and fast - just check if the app is running
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        environment=settings.app_env,
        checks={"app": "ok"}
    )


@app.get("/health/ready", response_model=HealthResponse, tags=["Health"])
async def readiness_check():
    """
    Readiness probe endpoint.
    
    AI Learning Note:
    - Kubernetes uses this to know if the pod can receive traffic
    - Checks dependencies (OpenAI, Search, etc.)
    - If this fails, K8s removes pod from service load balancer
    """
    checks = {}
    all_healthy = True
    
    # Check Azure OpenAI connectivity
    try:
        # We'll do a lightweight check - just verify we can create client
        from .llm_client import get_llm_client
        get_llm_client()
        checks["azure_openai"] = "ok"
    except Exception as e:
        checks["azure_openai"] = f"error: {str(e)}"
        all_healthy = False
    
    # Check Azure AI Search connectivity
    try:
        from .vector_store import get_vector_store
        get_vector_store()
        checks["azure_search"] = "ok"
    except Exception as e:
        checks["azure_search"] = f"error: {str(e)}"
        all_healthy = False
    
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_healthy else "not_ready",
            "version": "1.0.0",
            "environment": settings.app_env,
            "checks": checks
        }
    )


# =============================================================================
# RAG Endpoints
# =============================================================================

@app.post("/api/v1/query", response_model=QueryResponse, tags=["RAG"])
async def query(request: QueryRequest):
    """
    Main RAG query endpoint.
    
    Process:
    1. Embed the user query
    2. Search vector store for relevant documents
    3. Augment prompt with retrieved context
    4. Generate response with LLM
    
    AI Learning Note:
    - This is the core RAG flow in action
    - Track tokens and costs for production monitoring
    - Cache responses to reduce LLM calls and costs
    """
    try:
        from .rag_pipeline import RAGPipeline
        
        pipeline = RAGPipeline()
        
        # Override top_k if specified
        top_k = request.top_k or settings.top_k_results
        
        # Execute RAG pipeline
        response = await pipeline.query(
            question=request.query,
            top_k=top_k
        )
        
        # Handle both dict (from cache) and RAGResponse object
        if isinstance(response, dict):
            return QueryResponse(
                answer=response["answer"],
                sources=response.get("sources", []) if request.include_sources else [],
                metadata=response.get("metadata", {})
            )
        else:
            return QueryResponse(
                answer=response.answer,
                sources=response.sources if request.include_sources else [],
                metadata=response.to_dict().get("metadata", {})
            )
        
    except Exception as e:
        logger.error("RAG query failed", error=str(e), query=request.query)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}"
        )


@app.get("/api/v1/stats", tags=["Admin"])
async def get_stats():
    """
    Get system statistics.
    
    AI Learning Note:
    - Monitor token usage to track costs
    - Cache hit rates indicate efficiency
    - Use for capacity planning
    """
    return {
        "status": "ok",
        "config": {
            "model": settings.azure_openai_deployment_name,
            "embedding_model": settings.azure_openai_embedding_deployment,
            "chunk_size": settings.chunk_size,
            "top_k": settings.top_k_results,
        },
        "message": "Stats endpoint - production would include metrics from Prometheus"
    }


class ChatRequest(BaseModel):
    """Simple chat request without RAG."""
    message: str = Field(..., min_length=1, max_length=2000)
    
    class Config:
        json_schema_extra = {"example": {"message": "What is Kubernetes?"}}


@app.post("/api/v1/chat", tags=["LLM"])
async def chat(request: ChatRequest):
    """
    Direct LLM chat endpoint (no RAG/vector search).
    Use this to test Azure OpenAI connection directly.
    """
    try:
        from .llm_client import get_llm_client
        
        llm = get_llm_client()
        response = await llm.chat(
            user_message=request.message,
            temperature=0.7
        )
        
        return {
            "answer": response.content,
            "model": settings.azure_openai_deployment_name,
            "tokens": {
                "input": response.input_tokens,
                "output": response.output_tokens,
                "total": response.total_tokens
            },
            "estimated_cost_usd": response.estimated_cost_usd
        }
    except Exception as e:
        logger.error("Chat failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}"
        )


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        path=request.url.path,
        method=request.method
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.app_env != "production" else "An error occurred"
        }
    )


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "environment": settings.app_env,
        "docs": "/docs" if settings.app_env != "production" else "disabled",
        "endpoints": {
            "health": "/health",
            "readiness": "/health/ready",
            "query": "/api/v1/query",
            "stats": "/api/v1/stats"
        }
    }
