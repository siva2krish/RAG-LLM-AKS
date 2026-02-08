#!/bin/bash
# =============================================================================
# Deploy Infrastructure with Cost Estimation
# =============================================================================
# This script:
# 1. Shows cost estimate via Infracost
# 2. Asks for confirmation
# 3. Deploys via Terraform
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infrastructure/terraform"
ENV="${1:-dev}"
TFVARS_FILE="$TF_DIR/environments/${ENV}.tfvars"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         RAG+LLM Infrastructure Deployment                    ║"
echo "║         Environment: ${ENV}                                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check Azure login
echo -e "${YELLOW}🔐 Checking Azure CLI login...${NC}"
az account show > /dev/null 2>&1 || { echo -e "${RED}❌ Please run 'az login' first${NC}"; exit 1; }
SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "${GREEN}✅ Using subscription: $SUBSCRIPTION${NC}"
echo ""

# Check tfvars file exists
if [ ! -f "$TFVARS_FILE" ]; then
    echo -e "${RED}❌ Environment file not found: $TFVARS_FILE${NC}"
    echo "Available environments:"
    ls -1 "$TF_DIR/environments/"
    exit 1
fi

cd "$TF_DIR"

# Initialize Terraform
echo -e "${YELLOW}📦 Initializing Terraform...${NC}"
terraform init -upgrade

# =============================================================================
# Cost Estimation with Infracost
# =============================================================================
echo ""
echo -e "${YELLOW}💰 Estimating costs with Infracost...${NC}"
echo ""

if command -v infracost &> /dev/null; then
    # Run Infracost
    infracost breakdown --path . \
        --terraform-var-file="$TFVARS_FILE" \
        --format table
    
    echo ""
    echo -e "${BLUE}📊 Detailed cost breakdown saved to: infracost-report.json${NC}"
    infracost breakdown --path . \
        --terraform-var-file="$TFVARS_FILE" \
        --format json \
        --out-file infracost-report.json 2>/dev/null
else
    echo -e "${YELLOW}⚠️  Infracost not installed. Install with: brew install infracost${NC}"
    echo ""
    echo -e "${BLUE}📊 Manual Cost Estimate (Dev Environment):${NC}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║ Resource              │ SKU/Tier      │ Est. Cost            ║"
    echo "╠═══════════════════════╪═══════════════╪══════════════════════╣"
    echo "║ Azure OpenAI          │ S0 (pay/use)  │ ~\$5-20 (usage)      ║"
    echo "║ Azure AI Search       │ Free          │ \$0                  ║"
    echo "║ AKS (1x B2s node)     │ Free tier     │ ~\$30                ║"
    echo "║ Container Registry    │ Basic         │ ~\$5                 ║"
    echo "║ Storage Account       │ LRS           │ ~\$1                 ║"
    echo "║ Key Vault             │ Standard      │ ~\$0.03/10K ops      ║"
    echo "║ Log Analytics         │ PerGB         │ ~\$2-5               ║"
    echo "╠═══════════════════════╧═══════════════╧══════════════════════╣"
    echo "║ TOTAL ESTIMATED                       │ ~\$45-65/month       ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
fi

# =============================================================================
# Terraform Plan
# =============================================================================
echo ""
echo -e "${YELLOW}📋 Creating Terraform plan...${NC}"
terraform plan -var-file="$TFVARS_FILE" -out=tfplan

# =============================================================================
# Confirmation
# =============================================================================
echo ""
echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
echo -e "${RED}⚠️  CONFIRMATION REQUIRED${NC}"
echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Environment: ${GREEN}${ENV}${NC}"
echo -e "Subscription: ${GREEN}${SUBSCRIPTION}${NC}"
echo ""
read -p "Do you want to apply this infrastructure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}❌ Deployment cancelled.${NC}"
    rm -f tfplan
    exit 0
fi

# =============================================================================
# Apply
# =============================================================================
echo ""
echo -e "${GREEN}🚀 Applying Terraform...${NC}"
terraform apply tfplan

# Cleanup plan file
rm -f tfplan

# =============================================================================
# Generate .env file
# =============================================================================
echo ""
echo -e "${YELLOW}📝 Generating .env file...${NC}"
terraform output -raw env_file_content > "$SCRIPT_DIR/../.env" 2>/dev/null || true
echo -e "${GREEN}✅ .env file created at project root${NC}"

# =============================================================================
# Get AKS credentials
# =============================================================================
echo ""
echo -e "${YELLOW}🔑 Getting AKS credentials...${NC}"
eval "$(terraform output -raw aks_get_credentials_command)" 2>/dev/null || true

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✅ DEPLOYMENT COMPLETE!                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📋 Resources Created:${NC}"
terraform output resource_group_name
echo ""
echo -e "${BLUE}🔗 OpenAI Endpoint:${NC}"
terraform output openai_endpoint
echo ""
echo -e "${BLUE}💡 Next Steps:${NC}"
echo "1. Build and push Docker image:"
echo "   docker build -t \$(terraform output -raw acr_login_server)/rag-api:latest ."
echo "   docker push \$(terraform output -raw acr_login_server)/rag-api:latest"
echo ""
echo "2. Deploy to AKS:"
echo "   kubectl apply -f ../helm/rag-system/"
echo ""
echo -e "${YELLOW}💰 Cost Tip: Stop AKS when not in use:${NC}"
echo "   ./scripts/stop-aks.sh"
