#!/bin/bash
# =============================================================================
# Azure Resource Provider Registration Script
# =============================================================================
# Run this FIRST before deploying any Azure resources
# Registration can take 1-5 minutes per provider
# =============================================================================

set -e

echo "🔐 Checking Azure CLI login status..."
az account show > /dev/null 2>&1 || { echo "❌ Please run 'az login' first"; exit 1; }

SUBSCRIPTION=$(az account show --query name -o tsv)
echo "✅ Using subscription: $SUBSCRIPTION"
echo ""

# =============================================================================
# Required Resource Providers for RAG+LLM on AKS
# =============================================================================

declare -A PROVIDERS=(
    # Core AI Services
    ["Microsoft.CognitiveServices"]="Azure OpenAI, GPT models, Embeddings"
    ["Microsoft.Search"]="Azure AI Search (Vector Store)"
    
    # Kubernetes & Containers
    ["Microsoft.ContainerService"]="Azure Kubernetes Service (AKS)"
    ["Microsoft.ContainerRegistry"]="Azure Container Registry (ACR)"
    
    # Storage & Data
    ["Microsoft.Storage"]="Blob Storage for documents"
    ["Microsoft.Cache"]="Azure Cache for Redis"
    
    # Security
    ["Microsoft.KeyVault"]="Secrets & certificates management"
    ["Microsoft.ManagedIdentity"]="Workload Identity for AKS"
    
    # Networking
    ["Microsoft.Network"]="VNet, Load Balancer, Private Endpoints"
    
    # Monitoring & Observability
    ["Microsoft.OperationalInsights"]="Log Analytics workspace"
    ["Microsoft.Insights"]="Azure Monitor, Application Insights"
    ["Microsoft.AlertsManagement"]="Alert rules"
    
    # Optional but recommended
    ["Microsoft.Monitor"]="Azure Managed Grafana & Prometheus"
)

echo "📋 Checking and registering ${#PROVIDERS[@]} resource providers..."
echo "=============================================================="
echo ""

for provider in "${!PROVIDERS[@]}"; do
    description="${PROVIDERS[$provider]}"
    status=$(az provider show -n "$provider" --query "registrationState" -o tsv 2>/dev/null || echo "NotRegistered")
    
    if [ "$status" == "Registered" ]; then
        echo "✅ $provider - Already registered"
        echo "   └── $description"
    else
        echo "⏳ $provider - Registering..."
        echo "   └── $description"
        az provider register --namespace "$provider" --wait
        echo "   └── ✅ Registration complete"
    fi
    echo ""
done

# =============================================================================
# Special: Azure OpenAI Access Request
# =============================================================================
echo "=============================================================="
echo "⚠️  IMPORTANT: Azure OpenAI Access"
echo "=============================================================="
echo ""
echo "Azure OpenAI requires ADDITIONAL approval beyond resource providers."
echo ""
echo "📝 Request access here:"
echo "   https://aka.ms/oai/access"
echo ""
echo "Typical approval time: 1-5 business days"
echo ""
echo "Once approved, you can deploy Azure OpenAI in these regions:"
echo "   - East US, East US 2"
echo "   - West US, West US 3"  
echo "   - North Central US, South Central US"
echo "   - Sweden Central, France Central"
echo "   - UK South, Australia East"
echo ""

# =============================================================================
# Verify All Providers
# =============================================================================
echo "=============================================================="
echo "📊 Final Status Check"
echo "=============================================================="
echo ""

all_registered=true
for provider in "${!PROVIDERS[@]}"; do
    status=$(az provider show -n "$provider" --query "registrationState" -o tsv 2>/dev/null)
    if [ "$status" == "Registered" ]; then
        echo "✅ $provider"
    else
        echo "⏳ $provider - Status: $status (may take a few minutes)"
        all_registered=false
    fi
done

echo ""
if [ "$all_registered" = true ]; then
    echo "🎉 All resource providers are registered! You're ready to deploy."
else
    echo "⏳ Some providers are still registering. Run this script again in 5 minutes."
fi

echo ""
echo "=============================================================="
echo "🚀 Next Steps:"
echo "=============================================================="
echo "1. Request Azure OpenAI access (if not already approved)"
echo "2. Run: ./scripts/02-create-infrastructure.sh"
echo "3. Configure your .env file with the created resources"
echo ""
