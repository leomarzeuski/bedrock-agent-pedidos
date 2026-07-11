output "agent_id" {
  value = aws_bedrockagent_agent.this.agent_id
}

output "agent_alias_id" {
  value = aws_bedrockagent_agent_alias.dev.agent_alias_id
}

output "lambda_function" {
  value = aws_lambda_function.actions.function_name
}

output "invoke_example" {
  value = "aws bedrock-agent-runtime invoke-agent --agent-id ${aws_bedrockagent_agent.this.agent_id} --agent-alias-id ${aws_bedrockagent_agent_alias.dev.agent_alias_id} --session-id teste-01 --input-text 'oi, quero fazer um pedido' --region ${var.region} resposta.json"
}
