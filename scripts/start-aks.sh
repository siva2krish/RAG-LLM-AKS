#!/bin/bash
# =============================================================================
# Start AKS Cluster
# =============================================================================
# Resume the AKS cluster after stopping
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infrastructure/terraform"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

cd "$TF_DIR"

# Get resource names from Terraform state
RG_NAME=$(terraform output -raw resource_group_name 2>/dev/null)
AKS_NAME=$(terraform output -raw aks_cluster_name 2>/dev/null)

if [ -z "$RG_NAME" ] || [ -z "$AKS_NAME" ]; then
    echo -e "${YELLOW}⚠️  Could not find AKS cluster. Is infrastructure deployed?${NC}"
    exit 1
fi

echo -e "${YELLOW}▶️  Starting AKS cluster: $AKS_NAME${NC}"
echo "This may take 2-5 minutes..."
echo ""

az aks start \
    --resource-group "$RG_NAME" \
    --name "$AKS_NAME"

# Refresh kubectl credentials
echo -e "${YELLOW}🔑 Refreshing kubectl credentials...${NC}"
az aks get-credentials \
    --resource-group "$RG_NAME" \
    --name "$AKS_NAME" \
    --overwrite-existing

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ✅ AKS CLUSTER STARTED                               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Cluster status:${NC}"
kubectl get nodes

echo ""
echo -e "${YELLOW}💡 Remember to stop when done: ./scripts/stop-aks.sh${NC}"
