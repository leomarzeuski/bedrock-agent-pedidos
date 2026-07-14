# API HTTP: uma Lambda "wrapper" que embrulha o agente (invoke_agent) e a expoe
# por uma Function URL. Separada da Lambda de negocio (aws_lambda_function.actions),
# que e chamada PELO Bedrock. Esta aqui e um CLIENTE do agente.

data "archive_file" "api" {
  type        = "zip"
  source_dir  = "${path.module}/api"
  output_path = "${path.module}/api_payload.zip"
  excludes    = ["__pycache__", "**/*.pyc"]
}

# Chave da API: gerada aqui (fora do git). Override opcional via var.api_key.
resource "random_password" "api_key" {
  length  = 40
  special = false
}

locals {
  api_key = coalesce(var.api_key, random_password.api_key.result)
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.agent_name}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.12"
  handler          = "app.lambda_handler"
  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256
  timeout          = 120 # um turno encadeia varias tools (CEP, cotacao, pedido)
  memory_size      = 128

  environment {
    variables = {
      AGENT_ID = aws_bedrockagent_agent.this.agent_id
      ALIAS_ID = aws_bedrockagent_agent_alias.dev.agent_alias_id
      API_KEY  = local.api_key
    }
  }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE" # a gate real de acesso e o header x-api-key na Lambda

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST"]
    allow_headers = ["content-type", "x-api-key"]
    max_age       = 3600
  }
}

# Function URL com AuthType NONE precisa desta permissao publica explicita.
resource "aws_lambda_permission" "api_url_public" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
