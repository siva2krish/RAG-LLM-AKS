#!/bin/bash
# =============================================================================
# Destroy All Infrastructure
# =============================================================================
# Use this to completely remove all Azure resources and stop costs
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infrastructure/terraform"
ENV="${1:-dev}"
TFVARS_FILE="$TF_DIR/environments/${ENV}.tfvars"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         ⚠️  DESTROY ALL INFRASTRUCTURE                       ║"
echo "║         Environment: ${ENV}                                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

cd "$TF_DIR"

# Show what will be destroyed
echo -e "${YELLOW}📋 Resources that will be DESTROYED:${NC}"
terraform state list 2>/dev/null || echo "No state file found"

echo ""
echo -e "${RED}════════════════════════════════════════════════════════════════${NC}"
echo -e "${RED}⚠️  WARNING: This will DELETE ALL resources and data!${NC}"
echo -e "${RED}════════════════════════════════════════════════════════════════${NC}"
echo ""
read -p "Type 'destroy' to confirm: " confirm

if [ "$confirm" != "destroy" ]; then
    echo -e "${GREEN}❌ Destroy cancelled.${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}🗑️  Destroying infrastructure...${NC}"
terraform destroy -var-file="$TFVARS_FILE" -auto-approve

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ✅ ALL RESOURCES DESTROYED                           ║${NC}"
echo -e "${GREEN}║         Monthly cost: \$0                                     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}To recreate, run: ./scripts/deploy-infrastructure.sh ${ENV}${NC}"
