#!/bin/bash
# =============================================================================
# Stop AKS Cluster (Save ~$30/month when not in use)
# =============================================================================
# AKS nodes cost money even when idle. Stop them when not learning!
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

echo -e "${YELLOW}⏸️  Stopping AKS cluster: $AKS_NAME${NC}"
echo "This will deallocate all nodes and stop compute charges."
echo ""

az aks stop \
    --resource-group "$RG_NAME" \
    --name "$AKS_NAME"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ✅ AKS CLUSTER STOPPED                               ║${NC}"
echo -e "${GREEN}║         Compute charges: \$0 (while stopped)                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}To restart: ./scripts/start-aks.sh${NC}"
echo ""
echo -e "${YELLOW}Note: Storage and other resources still incur minimal charges.${NC}"
echo -e "${YELLOW}For zero cost, run: ./scripts/destroy-infrastructure.sh${NC}"
