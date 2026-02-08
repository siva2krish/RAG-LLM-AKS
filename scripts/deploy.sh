#!/bin/bash
# =============================================================================
# 🚀 FULL DEPLOYMENT SCRIPT - RAG+LLM System on Azure AKS
# =============================================================================
# Deploys everything from scratch:
#   1. Azure infrastructure (Terraform)
#   2. Docker images (RAG API, Chat UI, Ingestion Worker)
#   3. NGINX Ingress (Internal LB only)
#   4. KEDA (Autoscaling)
#   5. Redis (In-cluster cache)
#   6. Monitoring (Prometheus + Grafana)
#   7. RAG API + Chat UI + Ingestion Worker (Helm)
#   8. Search index + seed documents
#   9. Delete NetworkWatcherRG if created
#
# Usage: ./scripts/deploy.sh
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$PROJECT_DIR/infrastructure/terraform"
HELM_DIR="$PROJECT_DIR/infrastructure/helm"
NAMESPACE="rag-system"
MONITORING_NS="monitoring"
IMAGE_TAG="v1.0.0"

log()  { echo -e "${GREEN}[✅ $(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠️  $(date +%H:%M:%S)]${NC} $1"; }
info() { echo -e "${BLUE}[📌 $(date +%H:%M:%S)]${NC} $1"; }
step() { echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"; }

DEPLOY_START=$(date +%s)

# ============================================================================
step "Step 0/10: Infrastructure Cost Estimate"
# ============================================================================
cd "$TF_DIR"

if [ ! -d ".terraform" ]; then
    info "Running terraform init..."
    terraform init
fi

if command -v infracost &>/dev/null; then
    info "Running infracost estimate..."
    echo ""
    infracost breakdown --path=. --terraform-var-file=environments/dev.tfvars --format table 2>/dev/null || warn "Infracost failed (non-blocking)"
    echo ""
    read -p "💰 Review costs above. Continue deployment? (yes/no): " COST_CONFIRM
    if [ "$COST_CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
else
    warn "infracost not installed — skipping cost estimate"
    warn "Install: brew install infracost && infracost auth login"
fi

# ============================================================================
step "Step 1/10: Deploy Azure Infrastructure (Terraform)"
# ============================================================================
cd "$TF_DIR"

info "Running terraform apply..."
terraform apply -var-file=environments/dev.tfvars -auto-approve

# Capture outputs
RESOURCE_GROUP=$(terraform output -raw resource_group_name)
AKS_NAME=$(terraform output -raw aks_cluster_name)
ACR_SERVER=$(terraform output -raw acr_login_server)
ACR_NAME=$(echo "$ACR_SERVER" | cut -d'.' -f1)
OPENAI_ENDPOINT=$(terraform output -raw openai_endpoint)
OPENAI_KEY=$(terraform output -raw openai_key)
SEARCH_ENDPOINT=$(terraform output -raw search_endpoint)
SEARCH_KEY=$(terraform output -raw search_key)
STORAGE_CONN=$(terraform output -raw storage_connection_string)

log "Infrastructure deployed: RG=$RESOURCE_GROUP, AKS=$AKS_NAME"

# ============================================================================
step "Step 2/10: Configure kubectl"
# ============================================================================
az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" --overwrite-existing
kubectl get nodes
log "kubectl configured"

# ============================================================================
step "Step 3/10: Build & Push Docker Images"
# ============================================================================
cd "$PROJECT_DIR"
az acr login --name "$ACR_NAME"

info "Building RAG API image..."
docker build --platform linux/amd64 -t "$ACR_SERVER/rag-api:$IMAGE_TAG" .
docker push "$ACR_SERVER/rag-api:$IMAGE_TAG"
log "RAG API image pushed"

info "Building Chat UI image..."
docker build --platform linux/amd64 -f Dockerfile.chat-ui -t "$ACR_SERVER/rag-chat-ui:$IMAGE_TAG" .
docker push "$ACR_SERVER/rag-chat-ui:$IMAGE_TAG"
log "Chat UI image pushed"

info "Building Ingestion Worker image..."
docker build --platform linux/amd64 -f Dockerfile.ingestion -t "$ACR_SERVER/ingestion-worker:$IMAGE_TAG" .
docker push "$ACR_SERVER/ingestion-worker:$IMAGE_TAG"
log "Ingestion Worker image pushed"

# ============================================================================
step "Step 4/10: Install NGINX Ingress (Internal LoadBalancer)"
# ============================================================================
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update

helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.service.annotations."service\.beta\.kubernetes\.io/azure-load-balancer-internal"="true" \
  --set controller.service.externalTrafficPolicy=Local \
  --wait --timeout 120s

log "NGINX Ingress installed (Internal LB only)"

# ============================================================================
step "Step 5/10: Install KEDA (Autoscaling)"
# ============================================================================
helm repo add kedacore https://kedacore.github.io/charts 2>/dev/null || true
helm repo update

helm upgrade --install keda kedacore/keda \
  --namespace keda \
  --create-namespace \
  --wait --timeout 120s

log "KEDA installed"

# ============================================================================
step "Step 6/10: Deploy Redis (In-Cluster Cache)"
# ============================================================================
helm upgrade --install redis "$HELM_DIR/redis" \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --wait --timeout 60s

log "Redis deployed in-cluster"

# ============================================================================
step "Step 7/10: Deploy Monitoring (Prometheus + Grafana)"
# ============================================================================
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update

helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace "$MONITORING_NS" \
  --create-namespace \
  -f "$HELM_DIR/monitoring-values.yaml" \
  --wait --timeout 180s

log "Prometheus + Grafana deployed"

# ============================================================================
step "Step 8/10: Deploy RAG System (API + Chat UI + Ingestion Worker)"
# ============================================================================

info "Deploying RAG API..."
helm upgrade --install rag-system "$HELM_DIR/rag-system" \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --set image.repository="$ACR_SERVER/rag-api" \
  --set image.tag="$IMAGE_TAG" \
  --set azure.openai.endpoint="$OPENAI_ENDPOINT" \
  --set azure.search.endpoint="$SEARCH_ENDPOINT" \
  --set secrets.azureOpenaiApiKey="$OPENAI_KEY" \
  --set secrets.azureSearchKey="$SEARCH_KEY" \
  --set secrets.azureStorageConnectionString="$STORAGE_CONN" \
  --wait --timeout 120s

info "Deploying Chat UI..."
helm upgrade --install rag-chat-ui "$HELM_DIR/rag-chat-ui" \
  --namespace "$NAMESPACE" \
  --set image.repository="$ACR_SERVER/rag-chat-ui" \
  --set image.tag="$IMAGE_TAG" \
  --wait --timeout 90s

info "Deploying Ingestion Worker..."
helm upgrade --install ingestion-worker "$HELM_DIR/ingestion-worker" \
  --namespace "$NAMESPACE" \
  --set image.repository="$ACR_SERVER/ingestion-worker" \
  --set image.tag="$IMAGE_TAG" \
  --wait --timeout 90s

log "All services deployed"

# ============================================================================
step "Step 9/10: Create Search Index & Seed Documents"
# ============================================================================

info "Waiting for RAG API pod to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=rag-system -n "$NAMESPACE" --timeout=120s

info "Creating search index and seeding documents..."
kubectl exec deploy/rag-system -n "$NAMESPACE" -- python -c "
from src.rag_api.vector_store import VectorStore
import asyncio

async def setup():
    vs = VectorStore()
    await vs.create_index_if_not_exists()
    print('Index created!')

    docs = [
        {'id': 'doc1', 'content': 'Azure Kubernetes Service (AKS) is a managed container orchestration service provided by Microsoft Azure. It simplifies deploying, managing, and scaling containerized applications using Kubernetes. AKS handles critical tasks like health monitoring and maintenance.', 'title': 'AKS Overview', 'source': 'azure-docs'},
        {'id': 'doc2', 'content': 'Retrieval-Augmented Generation (RAG) combines retrieval mechanisms with generative AI models. It retrieves relevant documents from a knowledge base and uses them as context for generating accurate, grounded responses. RAG reduces hallucination in LLM outputs.', 'title': 'RAG Pattern', 'source': 'ai-patterns'},
        {'id': 'doc3', 'content': 'KEDA (Kubernetes Event-Driven Autoscaling) enables fine-grained autoscaling for Kubernetes workloads. Unlike HPA which only uses CPU/memory, KEDA scales based on event sources like message queues, databases, or custom metrics.', 'title': 'KEDA Scaling', 'source': 'k8s-docs'},
        {'id': 'doc4', 'content': 'Azure OpenAI Service provides REST API access to OpenAI powerful language models including GPT-4, GPT-4o-mini, and embedding models like text-embedding-3-small. It runs on Azure infrastructure with enterprise security and compliance.', 'title': 'Azure OpenAI', 'source': 'azure-docs'},
        {'id': 'doc5', 'content': 'Vector search enables semantic similarity search by converting text into numerical vectors (embeddings) and finding the closest matches using algorithms like HNSW. Unlike keyword search, vector search understands meaning and context.', 'title': 'Vector Search', 'source': 'search-docs'},
        {'id': 'doc6', 'content': 'Azure CNI Overlay assigns pod IPs from an overlay network separate from the VNet. This provides better IP address management than traditional Azure CNI while maintaining native Azure networking performance. Pods can communicate across nodes efficiently.', 'title': 'Azure CNI Overlay', 'source': 'azure-docs'},
        {'id': 'doc7', 'content': 'Helm is the package manager for Kubernetes. Helm charts bundle related Kubernetes resources into a single deployable unit with templated values. This enables repeatable, version-controlled deployments across environments.', 'title': 'Helm Charts', 'source': 'k8s-docs'},
    ]
    await vs.index_documents(docs)
    print(f'Indexed {len(docs)} documents!')

asyncio.run(setup())
"

log "Search index created and seeded with 7 documents"

# ============================================================================
step "Step 10/10: Cleanup NetworkWatcherRG (if created)"
# ============================================================================

if az group show --name NetworkWatcherRG &>/dev/null; then
    warn "NetworkWatcherRG found — deleting..."
    az group delete --name NetworkWatcherRG --yes --no-wait
    log "NetworkWatcherRG deletion initiated"
else
    log "No NetworkWatcherRG found — clean!"
fi

# ============================================================================
# SUMMARY
# ============================================================================
DEPLOY_END=$(date +%s)
DEPLOY_DURATION=$((DEPLOY_END - DEPLOY_START))
DEPLOY_MINUTES=$((DEPLOY_DURATION / 60))
DEPLOY_SECONDS=$((DEPLOY_DURATION % 60))

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            🎉 DEPLOYMENT COMPLETE!                          ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Time: ${DEPLOY_MINUTES}m ${DEPLOY_SECONDS}s                                            ║${NC}"
echo -e "${GREEN}║  AKS:  ${AKS_NAME}$(printf '%*s' $((30 - ${#AKS_NAME})) '')║${NC}"
echo -e "${GREEN}║  Network: Azure CNI Overlay                                 ║${NC}"
echo -e "${GREEN}║  Ingress: Internal LB (no public IP)                        ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Services deployed:                                          ║${NC}"
echo -e "${GREEN}║    ✅ RAG API (FastAPI)                                      ║${NC}"
echo -e "${GREEN}║    ✅ Chat UI (Streamlit)                                    ║${NC}"
echo -e "${GREEN}║    ✅ Ingestion Worker                                       ║${NC}"
echo -e "${GREEN}║    ✅ Redis (In-cluster)                                     ║${NC}"
echo -e "${GREEN}║    ✅ Prometheus + Grafana                                   ║${NC}"
echo -e "${GREEN}║    ✅ NGINX Ingress (Internal)                               ║${NC}"
echo -e "${GREEN}║    ✅ KEDA (Autoscaling)                                     ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Access:                                                     ║${NC}"
echo -e "${GREEN}║    RAG API:  kubectl port-forward svc/rag-system 8000:80 -n $NAMESPACE  ║${NC}"
echo -e "${GREEN}║    Chat UI:  kubectl port-forward svc/rag-chat-ui 8501:80 -n $NAMESPACE ║${NC}"
echo -e "${GREEN}║    Grafana:  kubectl port-forward svc/monitoring-grafana 3000:80 -n $MONITORING_NS ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
