output "agent_id" {
  value = aws_bedrockagent_agent.this.agent_id
}

output "agent_alias_id" {
  value = aws_bedrockagent_agent_alias.dev.agent_alias_id
}

output "lambda_function" {
  value = aws_lambda_function.actions.function_name
}

output "como_testar" {
  value = "AGENT_ID=${aws_bedrockagent_agent.this.agent_id} ALIAS_ID=${aws_bedrockagent_agent_alias.dev.agent_alias_id} python3 invoke.py 'oi, quero fazer um pedido'"
}

output "api_url" {
  value = var.deploy_api ? aws_lambda_function_url.api[0].function_url : null
}

output "api_key" {
  value     = var.deploy_api ? local.api_key : null
  sensitive = true
}

output "como_testar_api" {
  value = var.deploy_api ? "curl -sS $(terraform output -raw api_url) -H \"x-api-key: $(terraform output -raw api_key)\" -H 'content-type: application/json' -d '{\"mensagem\":\"quais lojas voces tem?\"}'" : null
}
