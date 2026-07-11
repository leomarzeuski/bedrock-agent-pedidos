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
