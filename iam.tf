data "aws_caller_identity" "current" {}

resource "aws_iam_role" "agent" {
  name = "AmazonBedrockExecutionRoleForAgents_${var.agent_name}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:agent/*"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "agent_invoke_model" {
  name = "invoke-foundation-model"
  role = aws_iam_role.agent.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = [
        "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.foundation_model}",
        "arn:aws:bedrock:*::foundation-model/${trimprefix(var.foundation_model, "us.")}"
      ]
    }]
  })
}

resource "aws_iam_role" "lambda" {
  name = "${var.agent_name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Role da Lambda da API (wrapper): logs + permissao de invocar o agente pelo alias.
# Opcional: so sobe quando var.deploy_api = true.
resource "aws_iam_role" "api" {
  count = var.deploy_api ? 1 : 0
  name  = "${var.agent_name}-api"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "api_basic" {
  count      = var.deploy_api ? 1 : 0
  role       = aws_iam_role.api[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api_invoke_agent" {
  count = var.deploy_api ? 1 : 0
  name  = "invoke-agent"
  role  = aws_iam_role.api[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "bedrock:InvokeAgent"
      Resource = aws_bedrockagent_agent_alias.dev.agent_alias_arn
    }]
  })
}