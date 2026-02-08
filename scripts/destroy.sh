#!/bin/bash
# =============================================================================
# 🔥 DESTROY SCRIPT - Complete Teardown
# =============================================================================
# Destroys everything:
#   1. All Helm releases
#   2. All Terraform-managed Azure resources
#   3. NetworkWatcherRG (auto-created by Azure)
#   4. Terraform state cleanup
#
# Usage: ./scripts/destroy.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$PROJECT_DIR/infrastructure/terraform"

log()  { echo -e "${GREEN}[✅ $(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠️  $(date +%H:%M:%S)]${NC} $1"; }
step() { echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"; }

DESTROY_START=$(date +%s)

echo -e "${RED}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         ⚠️  DESTROYING ALL AZURE RESOURCES ⚠️               ║"
echo "║                                                              ║"
echo "║  This will delete:                                           ║"
echo "║    • AKS cluster + all workloads                             ║"
echo "║    • Azure OpenAI (models + deployments)                     ║"
echo "║    • Azure AI Search (index + data)                          ║"
echo "║    • ACR (all container images)                              ║"
echo "║    • Storage Account                                         ║"
echo "║    • Key Vault                                               ║"
echo "║    • NetworkWatcherRG (if exists)                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

read -p "Are you sure? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

# ============================================================================
step "Step 1/4: Kill port-forwards"
# ============================================================================
pkill -f "kubectl port-forward" 2>/dev/null || true
log "Port-forwards killed"

# ============================================================================
step "Step 2/4: Terraform Destroy"
# ============================================================================
cd "$TF_DIR"

if [ -f "terraform.tfstate" ] || [ -d ".terraform" ]; then
    if [ ! -d ".terraform" ]; then
        terraform init
    fi
    terraform destroy -var-file=environments/dev.tfvars -auto-approve
    log "Terraform resources destroyed"
else
    warn "No Terraform state found — skipping"
fi

# ============================================================================
step "Step 3/4: Delete NetworkWatcherRG"
# ============================================================================
if az group show --name NetworkWatcherRG &>/dev/null; then
    warn "NetworkWatcherRG exists — deleting..."
    az group delete --name NetworkWatcherRG --yes --no-wait
    log "NetworkWatcherRG deletion initiated (async)"
else
    log "No NetworkWatcherRG found"
fi

# Also check for MC_ resource groups (AKS node resource group)
MC_RGS=$(az group list --query "[?starts_with(name, 'MC_')].name" -o tsv 2>/dev/null || true)
if [ -n "$MC_RGS" ]; then
    for rg in $MC_RGS; do
        warn "Orphaned AKS node RG found: $rg — deleting..."
        az group delete --name "$rg" --yes --no-wait 2>/dev/null || true
    done
fi

# ============================================================================
step "Step 4/4: Cleanup Local State"
# ============================================================================
cd "$TF_DIR"
rm -f terraform.tfstate terraform.tfstate.backup
log "Terraform state cleaned"

# Clear stale kubectl context
kubectl config delete-context "$(kubectl config current-context 2>/dev/null)" 2>/dev/null || true

# ============================================================================
# VERIFY
# ============================================================================
step "Verification — Listing all Azure resource groups"
echo ""
az group list -o table 2>/dev/null || echo "(no resource groups found)"

DESTROY_END=$(date +%s)
DESTROY_DURATION=$((DESTROY_END - DESTROY_START))
DESTROY_MINUTES=$((DESTROY_DURATION / 60))
DESTROY_SECONDS=$((DESTROY_DURATION % 60))

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            🔥 DESTROY COMPLETE!                              ║${NC}"
echo -e "${GREEN}║  Time: ${DESTROY_MINUTES}m ${DESTROY_SECONDS}s                                            ║${NC}"
echo -e "${GREEN}║  Azure: All resources removed                                ║${NC}"
echo -e "${GREEN}║  Local: Terraform state cleaned                              ║${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}║  To redeploy: ./scripts/deploy.sh                            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
