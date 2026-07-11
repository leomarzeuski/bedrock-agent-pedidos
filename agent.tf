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
        description = "Consulta o cardapio. Sem categoria, retorna a lista de categorias. Com categoria, retorna os itens (id, nome, preco/tamanhos) daquela categoria"

        parameters {
          map_block_key = "categoria"
          type          = "string"
          description   = "Categoria: pizzas, hamburgueres, combos, porcoes, massas, japonesa, saladas, cafe_da_manha, bebidas ou sobremesas"
          required      = false
        }

        parameters {
          map_block_key = "loja"
          type          = "string"
          description   = "Opcional. Filtra itens vendidos na loja A ou B"
          required      = false
        }
      }

      functions {
        name        = "listar_lojas"
        description = "Lista as 2 lojas com endereco, horario de funcionamento, se estao abertas agora e frete"
      }

      functions {
        name        = "validar_cep"
        description = "Valida um CEP de entrega e retorna o endereco e as coordenadas correspondentes"

        parameters {
          map_block_key = "cep"
          type          = "string"
          description   = "CEP com 8 digitos, apenas numeros"
          required      = true
        }
      }

      functions {
        name        = "cotar_pedido"
        description = "Calcula o preco exato do pedido (itens, subtotal, frete e total) SEM registrar. Use para montar o resumo antes de confirmar"

        parameters {
          map_block_key = "loja"
          type          = "string"
          description   = "Loja A ou B"
          required      = true
        }

        parameters {
          map_block_key = "itens"
          type          = "string"
          description   = "Mesma lista de itens do criar_pedido: id|qtd|tamanho|borda|meio_a_meio|obs, itens separados por ';'. Ex.: 'bb05|3 ; pz04|1|grande|catupiry|pz01'"
          required      = true
        }

        parameters {
          map_block_key = "cep"
          type          = "string"
          description   = "CEP de entrega, 8 digitos"
          required      = true
        }

        parameters {
          map_block_key = "observacoes"
          type          = "string"
          description   = "Observacao geral do pedido (opcional)"
          required      = false
        }
      }

      functions {
        name        = "criar_pedido"
        description = "Registra o pedido. Valida loja aberta, itens disponiveis e CEP. Chamar somente apos confirmacao explicita do resumo"

        parameters {
          map_block_key = "loja"
          type          = "string"
          description   = "Loja escolhida: A ou B"
          required      = true
        }

        parameters {
          map_block_key = "itens"
          type          = "string"
          description   = "Itens separados por ';' e campos por '|' nesta ordem: id|qtd|tamanho|borda|meio_a_meio|obs. Apenas o id e obrigatorio. tamanho, borda e meio_a_meio sao so para pizza (meio_a_meio = id do 2o sabor). Ex.: 'bb05|3 ; hb01|2 ; pz04|1|grande|catupiry|pz01'"
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

        parameters {
          map_block_key = "observacoes"
          type          = "string"
          description   = "Observacao geral do pedido (opcional)"
          required      = false
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
