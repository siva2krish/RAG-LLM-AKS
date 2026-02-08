# =============================================================================
# Variables - COST OPTIMIZED DEFAULTS
# =============================================================================

variable "project_name" {
  description = "Project name used in resource naming"
  type        = string
  default     = "siva-rag"
}

variable "environment" {
  description = "Environment: dev, staging, prod"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus2"  # Good availability, reasonable pricing
}

variable "openai_location" {
  description = "Azure region for OpenAI (limited regions)"
  type        = string
  default     = "eastus2"  # Best model availability
}

variable "owner_email" {
  description = "Owner email for tagging"
  type        = string
  default     = "sivakrishnavemuri91@gmail.com"
}

variable "auto_destroy_tag" {
  description = "Tag value for auto-destroy scripts (e.g., 'true' for dev resources)"
  type        = string
  default     = "true"
}

# =============================================================================
# AKS Configuration - MINIMAL FOR LEARNING
# =============================================================================

variable "aks_node_count" {
  description = "Number of AKS nodes (1 is enough for learning)"
  type        = number
  default     = 1  # Start with 1 node!
}

variable "aks_vm_size" {
  description = "VM size for AKS nodes"
  type        = string
  default     = "Standard_B2s"  # Burstable, ~$30/month
  
  # Cost reference:
  # Standard_B2s  = ~$30/month (2 vCPU, 4GB) - RECOMMENDED FOR DEV
  # Standard_B2ms = ~$60/month (2 vCPU, 8GB) - If you need more memory
  # Standard_D2s_v3 = ~$70/month (2 vCPU, 8GB) - Production grade
}

variable "enable_autoscaling" {
  description = "Enable AKS autoscaling (can save costs when idle)"
  type        = bool
  default     = false  # Disabled for predictable costs
}

# =============================================================================
# Feature Flags - Enable/Disable expensive components
# =============================================================================

variable "enable_redis" {
  description = "Deploy Azure Redis Cache (adds ~$16/month minimum)"
  type        = bool
  default     = false  # Use in-cluster Redis for dev
}

variable "enable_monitoring" {
  description = "Enable Container Insights (adds ~$10-20/month)"
  type        = bool
  default     = false  # Use Prometheus in-cluster instead
}
