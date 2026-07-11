resource "aws_bedrockagent_agent" "this" {
  agent_name                  = var.agent_name
  agent_resource_role_arn     = aws_iam_role.agent.arn
  foundation_model            = var.foundation_model
  instruction                 = file("${path.module}/instructions.txt")
  idle_session_ttl_in_seconds = 600
  description                 = "Agente de pedidos - projeto de estudo"
}

resource "aws_bedrockagent_agent_action_group" "pedidos" {
  action_group_name          = "pedidos"
  agent_id                   = aws_bedrockagent_agent.this.agent_id
  agent_version              = "DRAFT"
  skip_resource_in_use_check = true
  prepare_agent              = true

  action_group_executor {
    lambda = aws_lambda_function.actions.arn
  }

  function_schema {
    member_functions {
      functions {
        name        = "consultar_cardapio"
        description = "Retorna o cardapio completo com id, nome, descricao e preco de cada item, alem da taxa de entrega"
      }

      functions {
        name        = "validar_cep"
        description = "Valida um CEP de entrega e retorna o endereco correspondente"

        parameters {
          map_block_key = "cep"
          type          = "string"
          description   = "CEP com 8 digitos, apenas numeros"
          required      = true
        }
      }

      functions {
        name        = "criar_pedido"
        description = "Registra o pedido do cliente. Chamar somente apos confirmacao explicita do resumo do pedido"

        parameters {
          map_block_key = "itens"
          type          = "string"
          description   = "JSON com a lista de itens no formato [{\"id\":\"x1\",\"qtd\":2}]"
          required      = true
        }

        parameters {
          map_block_key = "cep"
          type          = "string"
          description   = "CEP ja validado do endereco de entrega"
          required      = true
        }

        parameters {
          map_block_key = "nome_cliente"
          type          = "string"
          description   = "Nome do cliente"
          required      = true
        }
      }
    }
  }
}

resource "aws_bedrockagent_agent_alias" "dev" {
  agent_alias_name = "dev"
  agent_id         = aws_bedrockagent_agent.this.agent_id
  description      = "Alias de teste"

  depends_on = [aws_bedrockagent_agent_action_group.pedidos]
}
