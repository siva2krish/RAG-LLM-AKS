#!/bin/bash
# =============================================================================
# Show Current Infrastructure Costs
# =============================================================================
# Uses Infracost to show detailed cost breakdown
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infrastructure/terraform"
ENV="${1:-dev}"
TFVARS_FILE="$TF_DIR/environments/${ENV}.tfvars"

BLUE='\033[0;34m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         💰 INFRASTRUCTURE COST ANALYSIS                      ║"
echo "║         Environment: ${ENV}                                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

cd "$TF_DIR"

# Check if Infracost is installed
if ! command -v infracost &> /dev/null; then
    echo -e "${YELLOW}⚠️  Infracost not installed.${NC}"
    echo ""
    echo "Install Infracost for detailed cost analysis:"
    echo ""
    echo "  # macOS"
    echo "  brew install infracost"
    echo ""
    echo "  # Linux"
    echo "  curl -fsSL https://raw.githubusercontent.com/infracost/infracost/master/scripts/install.sh | sh"
    echo ""
    echo "  # Then authenticate"
    echo "  infracost auth login"
    echo ""
    
    # Show manual estimate
    echo -e "${BLUE}📊 Manual Cost Estimate (${ENV}):${NC}"
    echo ""
    if [ "$ENV" == "dev" ]; then
        cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║                    DEV ENVIRONMENT                           ║
╠══════════════════════════════════════════════════════════════╣
║ Resource              │ SKU/Tier      │ Est. Monthly Cost    ║
╠═══════════════════════╪═══════════════╪══════════════════════╣
║ Azure OpenAI          │ S0 (pay/use)  │ $5-20 (usage based)  ║
║ Azure AI Search       │ Free          │ $0                   ║
║ AKS (1x B2s node)     │ Free tier     │ ~$30                 ║
║ Container Registry    │ Basic         │ ~$5                  ║
║ Storage Account       │ LRS           │ ~$1                  ║
║ Key Vault             │ Standard      │ ~$0.03/10K ops       ║
║ Log Analytics         │ PerGB         │ ~$2-5                ║
╠═══════════════════════╧═══════════════╧══════════════════════╣
║ TOTAL ESTIMATED                       │ ~$45-65/month        ║
╚══════════════════════════════════════════════════════════════╝
EOF
    else
        cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║                    PROD ENVIRONMENT                          ║
╠══════════════════════════════════════════════════════════════╣
║ Resource              │ SKU/Tier      │ Est. Monthly Cost    ║
╠═══════════════════════╪═══════════════╪══════════════════════╣
║ Azure OpenAI          │ S0 (pay/use)  │ $20-100 (usage)      ║
║ Azure AI Search       │ Basic         │ ~$75                 ║
║ AKS (2x B2ms nodes)   │ Free tier     │ ~$120                ║
║ Container Registry    │ Basic         │ ~$5                  ║
║ Storage Account       │ LRS           │ ~$2                  ║
║ Key Vault             │ Standard      │ ~$0.10               ║
║ Log Analytics         │ PerGB         │ ~$10-20              ║
╠═══════════════════════╧═══════════════╧══════════════════════╣
║ TOTAL ESTIMATED                       │ ~$150-250/month      ║
╚══════════════════════════════════════════════════════════════╝
EOF
    fi
    exit 0
fi

# Run Infracost
echo -e "${YELLOW}📊 Running Infracost analysis...${NC}"
echo ""

infracost breakdown \
    --path . \
    --terraform-var-file="$TFVARS_FILE" \
    --format table

echo ""
echo -e "${GREEN}💡 Cost Saving Tips:${NC}"
echo ""
echo "1. Stop AKS when not in use:"
echo "   ./scripts/stop-aks.sh"
echo ""
echo "2. Use Free tier AI Search for dev (already configured)"
echo ""
echo "3. Destroy everything when taking a break:"
echo "   ./scripts/destroy-infrastructure.sh"
echo ""
echo "4. Monitor actual costs in Azure Portal:"
echo "   https://portal.azure.com/#blade/Microsoft_Azure_CostManagement/Menu/costanalysis"
