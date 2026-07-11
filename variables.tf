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
  default = "us.amazon.nova-lite-v1:0"
}