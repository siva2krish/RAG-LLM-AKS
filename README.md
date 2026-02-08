# 🚀 Production RAG+LLM System on Azure AKS

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AZURE KUBERNETES SERVICE (AKS)                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │                           INGRESS (NGINX / App Gateway)                     ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                        │                                         │
│         ┌──────────────────────────────┼──────────────────────────────┐         │
│         ▼                              ▼                              ▼         │
│  ┌─────────────┐              ┌─────────────┐              ┌─────────────┐      │
│  │   RAG API   │              │  Ingestion  │              │   Admin     │      │
│  │  (FastAPI)  │              │   Worker    │              │    UI       │      │
│  │  3 replicas │              │  2 replicas │              │  1 replica  │      │
│  └─────────────┘              └─────────────┘              └─────────────┘      │
│         │                              │                              │          │
│         └──────────────────────────────┼──────────────────────────────┘         │
│                                        │                                         │
│  ┌─────────────────────────────────────┼─────────────────────────────────────┐  │
│  │                         SHARED SERVICES                                    │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐              │  │
│  │  │  Redis    │  │ Prometheus│  │  Grafana  │  │  Jaeger   │              │  │
│  │  │  Cache    │  │  Metrics  │  │ Dashboards│  │  Tracing  │              │  │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘              │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
┌───────────────┐              ┌───────────────┐              ┌───────────────┐
│ Azure OpenAI  │              │Azure AI Search│              │  Azure Blob   │
│   (GPT-4o)    │              │ (Vector Store)│              │   Storage     │
│  Embeddings   │              │   Semantic    │              │  (Documents)  │
└───────────────┘              └───────────────┘              └───────────────┘
```

## 🎯 Learning Objectives (AI Upskilling)

### Module 1: Embeddings & Vector Search
- How text becomes vectors (semantic meaning)
- Cosine similarity and vector distance
- Chunking strategies for documents
- Azure AI Search vector capabilities

### Module 2: RAG Pipeline
- Document ingestion and preprocessing
- Retrieval strategies (hybrid search)
- Context window management
- Prompt engineering for RAG

### Module 3: LLM Integration
- Azure OpenAI API patterns
- Token management and costs
- Streaming responses
- Model selection (GPT-4o vs GPT-4o-mini)

### Module 4: Production Concerns
- Caching strategies (semantic cache)
- Rate limiting and quotas
- Observability and tracing
- A/B testing different models

## 📁 Project Structure

```
Siva-AI/
├── src/
│   ├── rag_api/              # Main RAG service (FastAPI)
│   ├── ingestion/            # Document processing workers
│   ├── common/               # Shared utilities
│   └── admin_ui/             # Streamlit admin dashboard
├── infrastructure/
│   ├── terraform/            # Azure infrastructure
│   └── helm/                 # Kubernetes Helm charts
├── .github/
│   └── workflows/            # CI/CD pipelines
├── tests/                    # Unit and integration tests
├── notebooks/                # Learning notebooks
└── docs/                     # Documentation
```

## 🚀 Quick Start

### Prerequisites
- Azure subscription with OpenAI access
- Azure CLI + kubectl configured
- Docker Desktop
- Python 3.11+

### Local Development
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your Azure credentials

# Run locally
uvicorn src.rag_api.main:app --reload
```

### Deploy to AKS
```bash
# Infrastructure
cd infrastructure/terraform
terraform init && terraform apply

# Application
helm upgrade --install rag-system ./infrastructure/helm/rag-system
```

## 📊 Key Metrics to Monitor

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| P95 Latency | < 2s | > 5s |
| Token Usage | Track | > 80% quota |
| Cache Hit Rate | > 60% | < 40% |
| Error Rate | < 1% | > 5% |
| Vector Search Latency | < 200ms | > 500ms |
