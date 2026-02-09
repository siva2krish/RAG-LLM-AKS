# I Built a Production RAG System on Azure AKS for $40/Month — Here's Every Decision I Made and Why

**A cloud architect's opinionated walkthrough: from blank terminal to 13 pods serving AI-powered answers, with cost breakdowns you can actually verify.**

---

Last month, I set out to build something specific: a Retrieval-Augmented Generation system that could run on Azure Kubernetes Service — not as a proof-of-concept that lives in a Jupyter notebook, but as a real, deployable platform with ingestion pipelines, caching, observability, and a chat interface. The kind of system you'd hand to a team and say "here, extend this."

The constraint I gave myself was equally specific: **keep the monthly bill under $50.**

This article walks through what I built, the trade-offs I navigated, and the decisions I'd make differently if I were doing it again. If you're evaluating RAG architectures on Azure, this should save you a few weeks of trial and error.

The full source is on GitHub: [RAG-LLM-AKS](https://github.com/siva2krish/RAG-LLM-AKS).

---

## What the system actually does

The platform implements the full RAG lifecycle:

1. **Ingest** — A background worker polls Azure Blob Storage, extracts text from uploaded documents, chunks them (1,000 characters, 200-character overlap), generates vector embeddings, and upserts them into Azure AI Search.
2. **Query** — A user sends a natural language question via the REST API or Chat UI. The system embeds the query, retrieves the top-K most relevant document chunks using hybrid search (vector + BM25), constructs an augmented prompt, and sends it to GPT-4o-mini. The response comes back with source attribution and cost metadata.
3. **Cache** — Identical queries hit Redis instead of making round-trips to OpenAI. First query: ~2 seconds. Cached: <10ms.

All of this runs on a single Azure Kubernetes Service node.

---

## The architecture at a glance

Rather than describe the architecture in prose, here's the full cloud topology:

<p align="center">
  <img src="https://raw.githubusercontent.com/siva2krish/RAG-LLM-AKS/main/docs/screenshots/architecture-cloud.png" alt="Cloud Architecture — Azure PaaS + AKS Kubernetes topology" width="100%">
  <br><em>Cloud architecture: Azure managed services on the left, AKS cluster with 13 pods across 4 namespaces on the right.</em>
</p>

Here's what's actually running:

**Azure PaaS layer (managed services):**
- Azure OpenAI — GPT-4o-mini for generation, text-embedding-3-small for vector embeddings
- Azure AI Search (Free tier) — HNSW vector index with hybrid search
- Azure Container Registry (Basic) — Docker image storage
- Azure Key Vault — Two secrets (OpenAI key, Search key)
- Azure Storage Account — Blob container for document ingestion
- Log Analytics — 30-day diagnostic retention

**Kubernetes layer (13 pods across 4 namespaces):**
- RAG API (FastAPI) — The query and chat endpoints
- Chat UI (Streamlit) — Interactive frontend
- Ingestion Worker — Background document processing
- Redis — In-cluster response cache
- NGINX Ingress Controller — Internal-only load balancer
- KEDA — Event-driven autoscaler (supports scale-to-zero)
- Prometheus + Grafana — Metrics and dashboards

Every component is deployed via Helm. Every Azure resource is provisioned via Terraform. The entire system goes from `az login` to serving queries in about 12 minutes.

---

## The decisions that actually matter

Architecture diagrams are nice. But the real value is in *why* you chose one path over another. Here are the decisions I spent the most time on — and the reasoning I'd present to a team or a hiring manager.

### 1. Azure CNI Overlay vs. kubenet vs. flat CNI

This was the first decision and the one with the longest tail.

**Kubenet** is the AKS default and it's free, but pods get IPs through a Linux bridge and traffic is routed via user-defined routes. It works, but it's slow, it doesn't support Azure Network Policies natively, and it scales poorly.

**Flat Azure CNI** assigns each pod an IP from your VNet subnet. Great for performance, but your subnet's IP space gets exhausted fast. A /24 gives you 251 IPs. With 13 pods, that sounds fine — until you realize each node reserves 30 IPs for future pods by default, and scaling to 3 nodes with 30 pods each means you need a /22 or bigger. I've seen teams burn an entire sprint re-architecting their network because they started with flat CNI and a too-small subnet.

**Azure CNI Overlay** is the sweet spot. Pods get IPs from a private overlay network (`192.168.0.0/16` in my case), completely independent of the VNet address space. You get Azure CNI performance, Azure Network Policy support, and zero risk of IP exhaustion. The only downside: overlay pod IPs aren't directly routable from on-premises networks. For this use case, that's irrelevant.

### 2. GPT-4o-mini instead of GPT-4o

This was a cost decision disguised as a quality decision.

GPT-4o-mini costs $0.15 per million input tokens. GPT-4o costs $2.50. That's a 16× difference. For a RAG system where the LLM's job is to synthesize information from retrieved context — not to reason from scratch — the quality gap is negligible. The context window does the heavy lifting. The model just needs to be coherent.

At development scale (~500K input tokens/month), the difference is $0.08 vs $1.25. At production scale (10K queries/day), it's $15 vs $250 per month. GPT-4o-mini is the right default until you have specific quality metrics proving otherwise.

### 3. In-cluster Redis vs. Azure Cache for Redis

Azure Cache for Redis starts at $16/month for the C0 Basic tier. An in-cluster Redis pod running on the existing node costs $0 in marginal compute — it's using resources that are already provisioned.

Is managed Redis better for production? Absolutely — you get persistence, replication, built-in monitoring, and an SLA. But for a development cluster where the cache is purely a performance optimization (not a data store), spending $16/month on something you can replace with a single `helm install` is hard to justify.

The migration path is trivial: change the `REDIS_URL` environment variable from `redis://redis-master:6379/0` to the Azure-managed endpoint. One config change, zero code changes.

### 4. NGINX Ingress with Internal LB vs. Application Gateway

Azure Application Gateway Ingress Controller (AGIC) is the "official" Azure way to do ingress on AKS. It's also $200+/month for the Application Gateway resource alone, and it adds a managed PaaS component outside your cluster that you need to coordinate with.

NGINX Ingress Controller runs in-cluster, is free, and does everything I need: path-based routing, SSL termination (when needed), and health-check-based backend selection. The Internal LoadBalancer annotation ensures there's no public IP — zero attack surface.

For production systems that need WAF (Web Application Firewall) capabilities, AGIC makes sense. For everything else, NGINX is the pragmatic choice.

### 5. kube-prometheus-stack vs. Azure Monitor

Azure Container Insights is the managed monitoring option for AKS. It's convenient but costs $10–20/month in Log Analytics ingestion, and the dashboards are Azure-native (not portable).

The kube-prometheus-stack gives you Prometheus for metrics collection, Grafana for dashboards, node-exporter for host-level metrics, and kube-state-metrics for cluster state. All running on the existing node at zero marginal cost. The dashboards are community-standard, portable, and more detailed than Container Insights for Kubernetes-specific observability.

The trade-off: you own the lifecycle. If Prometheus fills up the disk, that's your problem. At dev scale with 30-day retention, this hasn't been an issue.

---

## The cost model — verified, not estimated

I ran [Infracost](https://www.infracost.io/) against the live Terraform plan to verify the numbers. This matters because Azure pricing pages are notoriously ambiguous about what "free tier" actually includes.

### Fixed infrastructure: $40.17/month

| Resource | SKU | Monthly Cost |
|----------|-----|:------------:|
| AKS Control Plane | Free tier | $0 |
| AKS Node (1× Standard_B2s) | 2 vCPU, 4 GB RAM | $30.37 |
| Container Registry | Basic, 10 GB | $5.00 |
| Storage Account | Standard LRS | ~$1.00 |
| Log Analytics | PerGB2018, 30-day | ~$2–5 |
| Key Vault | Standard | ~$0.03 |
| Azure AI Search | Free tier | $0 |
| In-cluster (Redis, Prometheus, Grafana, KEDA, NGINX) | — | $0 |

### Variable AI cost: under $1/month at dev scale

| Model | Price | Dev Usage | Monthly |
|-------|-------|-----------|:-------:|
| GPT-4o-mini (input) | $0.15/1M tokens | ~500K tokens | ~$0.08 |
| GPT-4o-mini (output) | $0.60/1M tokens | ~200K tokens | ~$0.12 |
| text-embedding-3-small | $0.02/1M tokens | ~100K tokens | <$0.01 |

**Total: roughly $41/month.** And you can `az aks stop` the cluster when you're not using it to drop the compute cost to $0 — you only pay for storage and the PaaS services (which are mostly free-tier).

---

## The RAG pipeline — five stages, five modules

<p align="center">
  <img src="https://raw.githubusercontent.com/siva2krish/RAG-LLM-AKS/main/docs/screenshots/rag-pipeline-flow.png" alt="RAG Pipeline Flow — from user query to cached response" width="100%">
  <br><em>End-to-end RAG pipeline: Cache → Embed → Retrieve → Augment → Return.</em>
</p>

Every query follows a deterministic path through five stages. Each stage is a separate Python module, independently testable.

**Stage 1: Cache check.** Redis lookup by query hash. If hit, return immediately. If miss, proceed.

**Stage 2: Embed the query.** The user's question is converted to a 1,536-dimension vector using `text-embedding-3-small`. This costs $0.02 per million tokens — effectively free.

**Stage 3: Retrieve.** The embedding is sent to Azure AI Search, which performs hybrid retrieval: HNSW vector similarity *plus* BM25 keyword scoring. The top-K results (default 5, configurable per request) are returned with relevance scores.

**Stage 4: Augment and generate.** The retrieved chunks are injected into a prompt template and sent to GPT-4o-mini. The model generates a grounded answer based solely on the provided context — reducing hallucination risk.

**Stage 5: Return and cache.** The response is returned to the user with full metadata (sources, token count, cost, latency, cache status) and stored in Redis for future identical queries.

Here's what an actual response looks like from the live system:

```json
{
  "answer": "Kubernetes is an open-source container orchestration platform...",
  "sources": [
    {"id": "1", "title": "Kubernetes Overview", "score": 0.033},
    {"id": "2", "title": "Azure AKS", "score": 0.033},
    {"id": "3", "title": "Docker Containers", "score": 0.032}
  ],
  "metadata": {
    "retrieved_documents": 3,
    "total_tokens": 467,
    "estimated_cost_usd": 0.003665,
    "latency_ms": 1415,
    "from_cache": false
  }
}
```

Every response includes cost attribution. At $0.003 per query, you can run 13,000 queries before spending $50 on tokens. That's the kind of number a product manager can work with.

---

## The deployment experience

I wanted the entire system to go from zero to running with a single command. The deploy script runs 10 steps sequentially, each idempotent:

1. **Cost gate** — Runs Infracost, shows the estimate, asks for confirmation before spending anything.
2. **Terraform apply** — Provisions 15 Azure resources (~5 minutes).
3. **kubectl config** — Fetches AKS credentials.
4. **Docker build + push** — Builds 3 container images for `linux/amd64`, pushes to ACR (~3 minutes).
5. **NGINX Ingress** — Installs the controller with Internal LB annotation.
6. **KEDA** — Installs event-driven autoscaler.
7. **Redis** — Deploys in-cluster cache.
8. **Monitoring** — Deploys Prometheus + Grafana with lightweight resource limits.
9. **Application** — Deploys RAG API, Chat UI, and Ingestion Worker.
10. **Data seed** — Creates the search index and seeds 7 sample documents.

The teardown script reverses everything: Helm uninstalls → Terraform destroy → cleanup orphaned resource groups → wipe local state.

The entire lifecycle is captured in two scripts. No clicking through the Azure portal. No manual kubectl applies. No "works on my machine."

<p align="center">
  <img src="https://raw.githubusercontent.com/siva2krish/RAG-LLM-AKS/main/docs/screenshots/chat-ui.png" alt="Streamlit Chat UI" width="90%">
  <br><em>The Streamlit Chat UI in action — natural language queries with source attribution and cost metadata.</em>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/siva2krish/RAG-LLM-AKS/main/docs/screenshots/grafana-dashboard.png" alt="Grafana Dashboard" width="90%">
  <br><em>Grafana dashboard showing cluster health, pod metrics, and resource utilization — all running on the same B2s node.</em>
</p>

---

## What I'd change for production

This is a development-grade system by design. Here's what the upgrade path looks like:

| Area | Current (Dev) | Production Path |
|------|:------------:|:---------------:|
| AKS tier | Free (no SLA) | Standard ($75/mo, 99.95% SLA) |
| Node pool | 1× B2s (4 GB) | 3× D4s_v3 + autoscaling |
| Redis | In-cluster pod | Azure Cache for Redis (C1 Standard) |
| AI Search | Free (50 MB) | Basic ($75/mo) or Standard |
| Secrets | Key Vault + env vars | Key Vault CSI driver (pod-native injection) |
| Identity | System-assigned managed identity | Workload Identity (per-pod RBAC) |
| Ingress | NGINX + Internal LB | AGIC + WAF (if public-facing) |
| TLS | None (internal only) | cert-manager + Let's Encrypt |
| Registry | ACR Basic + admin auth | ACR Standard + RBAC |

Every one of these upgrades is a configuration change, not a re-architecture. That's deliberate. The system was designed so that dev and production differ in resource SKUs and security posture — not in topology.

---

## Lessons learned

**Embedding models are absurdly cheap.** At $0.02 per million tokens, `text-embedding-3-small` is essentially free. I embedded my entire document corpus for less than a penny. Don't over-optimize on the embedding side — spend your budget on the LLM.

**Cache hit rates matter more than model speed.** A cold GPT-4o-mini query takes ~2 seconds. A Redis cache hit takes <10ms. If even 30% of your queries are repeated (common in enterprise settings where teams ask similar questions), caching cuts your effective latency — and cost — dramatically.

**Azure CNI Overlay should be the default.** I started with kubenet, hit network policy limitations, switched to flat CNI, hit IP exhaustion warnings, and finally landed on CNI Overlay. It should have been the first choice. If you're starting a new AKS cluster today, use Overlay unless you have a specific reason not to.

**B2s nodes are surprisingly capable.** I was skeptical that a 2 vCPU / 4 GB RAM burstable VM could run 13 pods including Prometheus and Grafana. It does — with 40% memory headroom and 89% CPU headroom at idle. For development and staging workloads, don't reach for D-series by default.

**Observability is free if you plan for it.** The kube-prometheus-stack runs on the existing node at zero marginal cost. There's no excuse for a Kubernetes deployment without metrics. Adding it after the fact is always harder than including it from day one.

---

## Wrapping up

The complete system — infrastructure as code, application source, Helm charts, deployment scripts, and documentation — is in the [RAG-LLM-AKS repository](https://github.com/siva2krish/RAG-LLM-AKS). Fork it, break it, adapt it to your use case.

If you're building RAG systems on Azure, I hope this saves you some of the dead ends I walked into. The technology is mature enough now that the hard problems aren't "can we make it work" — they're "can we make it work at a cost and complexity level that a small team can sustain." That's the question this architecture tries to answer.

---

*Siva Vemuri is a Staff DevOps Lead/Architect with 11+ years of experience in cloud infrastructure, Kubernetes, and CI/CD. He holds CKA (Certified Kubernetes Administrator), AZ-400 (Azure DevOps Solutions), and RHCSA certifications, and has designed production AKS platforms across healthcare and telecom. Find more of his work on [GitHub](https://github.com/siva2krish).*
