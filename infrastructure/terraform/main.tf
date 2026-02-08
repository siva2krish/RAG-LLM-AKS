# =============================================================================
# RAG+LLM Infrastructure - COST OPTIMIZED
# =============================================================================
# Design Principles:
# 1. Use LOWEST viable SKUs for learning/dev
# 2. Easy to destroy and recreate
# 3. Pay-per-use where possible
# 4. No over-provisioning
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.85"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  
  # Optional: Remote state for team collaboration
  # backend "azurerm" {
  #   resource_group_name  = "tfstate-rg"
  #   storage_account_name = "tfstatesiva"
  #   container_name       = "tfstate"
  #   key                  = "rag-llm.tfstate"
  # }
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false  # Easy destroy
    }
    key_vault {
      purge_soft_delete_on_destroy = true  # Clean deletion
    }
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
  }
}

# =============================================================================
# Random suffix for unique names
# =============================================================================
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

locals {
  # Naming convention
  name_prefix = "${var.project_name}-${var.environment}"
  name_suffix = random_string.suffix.result
  
  # Common tags for cost tracking
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    CostCenter  = "AI-Learning"
    Owner       = var.owner_email
    AutoDestroy = var.auto_destroy_tag  # Tag for cleanup scripts
  }
}

# =============================================================================
# Resource Group
# =============================================================================
resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}-${local.name_suffix}"
  location = var.location
  tags     = local.common_tags
}

# =============================================================================
# Azure OpenAI - PAY PER USE (No fixed cost!)
# =============================================================================
resource "azurerm_cognitive_account" "openai" {
  name                  = "oai-${local.name_prefix}-${local.name_suffix}"
  location              = var.openai_location  # OpenAI has limited regions
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "OpenAI"
  sku_name              = "S0"  # Standard - PAY PER USE
  custom_subdomain_name = "oai-${local.name_prefix}-${local.name_suffix}"
  
  tags = local.common_tags
  
  lifecycle {
    ignore_changes = [tags]
  }
}

# GPT-4o-mini (CHEAPER than GPT-4o for learning)
resource "azurerm_cognitive_deployment" "gpt4o_mini" {
  name                 = "gpt-4o-mini"
  cognitive_account_id = azurerm_cognitive_account.openai.id
  
  model {
    format  = "OpenAI"
    name    = "gpt-4o-mini"
    version = "2024-07-18"
  }
  
  scale {
    type     = "Standard"
    capacity = 10  # 10K TPM - minimal for learning
  }
}

# Text Embedding (Required for RAG)
resource "azurerm_cognitive_deployment" "embedding" {
  name                 = "text-embedding-3-small"  # SMALL is cheaper!
  cognitive_account_id = azurerm_cognitive_account.openai.id
  
  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"  # $0.02/1M tokens vs $0.13 for large
    version = "1"
  }
  
  scale {
    type     = "Standard"
    capacity = 10  # 10K TPM
  }
}

# =============================================================================
# Azure AI Search - FREE TIER for Dev!
# =============================================================================
resource "azurerm_search_service" "main" {
  name                = "search-${local.name_prefix}-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  
  # FREE tier: 50MB storage, 3 indexes - enough for learning!
  sku = var.environment == "dev" ? "free" : "basic"
  
  replica_count   = 1
  partition_count = 1
  
  tags = local.common_tags
}

# =============================================================================
# Storage Account - MINIMAL TIER
# =============================================================================
resource "azurerm_storage_account" "main" {
  name                     = "st${replace(local.name_prefix, "-", "")}${local.name_suffix}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"  # Locally redundant - CHEAPEST
  
  # Cost saving options
  access_tier               = "Hot"
  min_tls_version           = "TLS1_2"
  https_traffic_only_enabled = true
  
  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
  
  tags = local.common_tags
}

resource "azurerm_storage_container" "documents" {
  name                  = "documents"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# =============================================================================
# Key Vault - STANDARD (no premium needed)
# =============================================================================
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                = "kv-${local.name_prefix}-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"  # Not premium
  
  purge_protection_enabled   = false  # Allow easy delete
  soft_delete_retention_days = 7      # Minimum retention
  
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id
    
    secret_permissions = ["Get", "List", "Set", "Delete", "Purge"]
    key_permissions    = ["Get", "List", "Create", "Delete"]
  }
  
  tags = local.common_tags
}

# Store OpenAI key in Key Vault
resource "azurerm_key_vault_secret" "openai_key" {
  name         = "openai-api-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "search_key" {
  name         = "search-api-key"
  value        = azurerm_search_service.main.primary_key
  key_vault_id = azurerm_key_vault.main.id
}

# =============================================================================
# Container Registry - BASIC tier
# =============================================================================
resource "azurerm_container_registry" "main" {
  name                = "acr${replace(local.name_prefix, "-", "")}${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"  # $5/month - cheapest
  admin_enabled       = true     # Simple auth for learning
  
  tags = local.common_tags
}

# =============================================================================
# AKS Cluster - MINIMAL CONFIGURATION
# =============================================================================
resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-${local.name_prefix}-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "aks-${local.name_prefix}"
  
  # Free tier for control plane!
  sku_tier = "Free"
  
  # ==========================================================================
  # API Server Access Control
  # ==========================================================================
  # Option 1: Private cluster (API server only reachable via VNet)
  #   - Requires jumpbox VM or VPN to access kubectl
  #   - Best for production
  private_cluster_enabled = var.aks_private_cluster
  
  # Option 2: Public API server with IP restriction (recommended for dev)
  #   - API server is public but ONLY your IP can reach it
  #   - No jumpbox needed, kubectl works from your laptop
  api_server_access_profile {
    authorized_ip_ranges = var.aks_private_cluster ? [] : var.aks_authorized_ip_ranges
  }
  
  default_node_pool {
    name                = "default"
    node_count          = var.aks_node_count
    vm_size             = var.aks_vm_size  # B2s = ~$30/month
    os_disk_size_gb     = 30               # Minimal disk
    os_disk_type        = "Managed"
    
    # Enable auto-scaling for cost optimization
    enable_auto_scaling = var.enable_autoscaling
    min_count           = var.enable_autoscaling ? 1 : null
    max_count           = var.enable_autoscaling ? 3 : null
    
    # Spot instances for non-prod (70% cheaper!)
    # Uncomment for maximum savings (but can be evicted)
    # priority        = "Spot"
    # eviction_policy = "Delete"
    # spot_max_price  = -1
  }
  
  identity {
    type = "SystemAssigned"
  }
  
  # Azure CNI Overlay - Modern networking with better IP management
  # Benefits over kubenet:
  # - Pods get IPs from overlay network (not VNet IPs)
  # - Better performance than kubenet
  # - Supports Network Policies natively
  # - Required for some advanced features
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"  # CNI Overlay mode
    network_policy      = "azure"    # Azure Network Policy
    pod_cidr            = "192.168.0.0/16"  # Overlay pod CIDR
    service_cidr        = "10.0.0.0/16"
    dns_service_ip      = "10.0.0.10"
  }
  
  tags = local.common_tags
}

# Attach ACR to AKS
resource "azurerm_role_assignment" "aks_acr" {
  principal_id                     = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  role_definition_name             = "AcrPull"
  scope                            = azurerm_container_registry.main.id
  skip_service_principal_aad_check = true
}

# =============================================================================
# Log Analytics - MINIMAL RETENTION
# =============================================================================
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name_prefix}-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30  # Minimum for cost
  
  tags = local.common_tags
}
