variable "region" {
  type    = string
  default = "us-east-1"
}

variable "agent_name" {
  type    = string
  default = "parla-deli"
}

variable "foundation_model" {
  type    = string
  default = "us.amazon.nova-pro-v1:0"
}

variable "deploy_api" {
  type        = bool
  default     = false
  description = "Se true, sobe tambem a API HTTP (Lambda wrapper + Function URL publica) que embrulha o agente. Default false: sobe so o agente Bedrock."
}

variable "api_key" {
  type        = string
  default     = null
  sensitive   = true
  description = "Chave da API HTTP (header x-api-key). Se null, o Terraform gera uma; leia com: terraform output -raw api_key. So usado quando deploy_api = true"
}