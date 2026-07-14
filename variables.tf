variable "region" {
  type    = string
  default = "us-east-1"
}

variable "agent_name" {
  type    = string
  default = "agente-pedidos"
}

variable "foundation_model" {
  type    = string
  default = "us.amazon.nova-pro-v1:0"
}

variable "api_key" {
  type        = string
  default     = null
  sensitive   = true
  description = "Chave da API HTTP (header x-api-key). Se null, o Terraform gera uma; leia com: terraform output -raw api_key"
}