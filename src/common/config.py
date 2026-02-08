"""
Configuration Management using Pydantic Settings
=================================================
Centralizes all configuration with validation and type safety.
Loads from environment variables with .env file support.

AI Learning Note:
-----------------
Production AI systems need careful configuration management:
- API keys and endpoints for LLM providers
- RAG parameters (chunk size, overlap, top_k)
- Rate limits to manage costs and quotas
"""

from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # --- Application ---
    app_env: str = Field(default="development", description="Environment: development, staging, production")
    app_name: str = Field(default="RAG-LLM-System", description="Application name")
    log_level: str = Field(default="INFO")
    cors_origins: List[str] = Field(default=["http://localhost:3000"])
    
    # --- Azure OpenAI ---
    azure_openai_endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    azure_openai_api_key: str = Field(..., description="Azure OpenAI API key")
    azure_openai_api_version: str = Field(default="2024-02-01")
    azure_openai_deployment_name: str = Field(default="gpt-4o", description="Chat model deployment")
    azure_openai_embedding_deployment: str = Field(default="text-embedding-3-large")
    
    # --- Azure AI Search ---
    azure_search_endpoint: str = Field(..., description="Azure AI Search endpoint")
    azure_search_api_key: str = Field(..., description="Azure AI Search admin key")
    azure_search_index_name: str = Field(default="rag-documents")
    
    # --- Azure Blob Storage ---
    azure_storage_connection_string: str = Field(..., description="Blob storage connection")
    azure_storage_container: str = Field(default="documents")
    
    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")
    
    # --- RAG Configuration ---
    # These parameters significantly affect RAG quality!
    chunk_size: int = Field(
        default=1000, 
        ge=100, 
        le=4000,
        description="Size of text chunks. Larger = more context, but less precise retrieval"
    )
    chunk_overlap: int = Field(
        default=200, 
        ge=0,
        description="Overlap between chunks to maintain context continuity"
    )
    top_k_results: int = Field(
        default=5, 
        ge=1, 
        le=20,
        description="Number of similar documents to retrieve"
    )
    similarity_threshold: float = Field(
        default=0.75, 
        ge=0.0, 
        le=1.0,
        description="Minimum similarity score for retrieved documents"
    )
    
    # --- Rate Limiting ---
    rate_limit_requests: int = Field(default=100)
    rate_limit_window_seconds: int = Field(default=60)
    
    # --- Observability ---
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")
    enable_tracing: bool = Field(default=True)
    
    @field_validator("app_env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v
    
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
    
    @property
    def embedding_dimensions(self) -> int:
        """Return embedding dimensions based on model."""
        # text-embedding-3-large = 3072, text-embedding-3-small = 1536
        if "large" in self.azure_openai_embedding_deployment:
            return 3072
        return 1536


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
