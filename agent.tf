resource "aws_bedrockagent_agent" "this" {
  agent_name                  = var.agent_name
  agent_resource_role_arn     = aws_iam_role.agent.arn
  foundation_model            = var.foundation_model
  instruction                 = file("${path.module}/instructions.txt")
  idle_session_ttl_in_seconds = 3600
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
          description   = "Categoria: pizzas, hamburgueres, combos, porcoes, salgados, massas, japonesa, saladas, cafe_da_manha, bebidas ou sobremesas"
          required      = false
        }

        parameters {
          map_block_key = "loja"
          type          = "string"
          description   = "Opcional. Filtra itens vendidos na unidade Aflitos ou Boa Viagem"
          required      = false
        }
      }

      functions {
        name        = "listar_lojas"
        description = "Lista as 2 lojas com endereco, horario de funcionamento, se estao abertas agora e frete"
      }

      functions {
        name        = "adicionar_itens"
        description = "Adiciona um ou mais itens ao carrinho e retorna o carrinho com precos, a loja escolhida e se ela esta aberta. Se a loja nao for informada, o sistema escolhe uma loja aberta que tenha os itens"

        parameters {
          map_block_key = "loja"
          type          = "string"
          description   = "Opcional. Unidade Aflitos ou Boa Viagem, apenas se a pessoa escolheu explicitamente. Se ela nao escolheu, deixe em branco que o sistema seleciona"
          required      = false
        }

        parameters {
          map_block_key = "itens"
          type          = "string"
          description   = "Itens separados por ';' e campos por '|' nesta ordem: id|qtd|tamanho|borda|meio_a_meio|obs. Apenas o id e obrigatorio; tamanho, borda e meio_a_meio sao so para pizza (meio_a_meio = id do 2o sabor) e devem ficar vazios nos demais itens ate chegar no obs. Salgados (por kg): qtd em GRAMAS ou com sufixo, ex.: 'sg01|500' ou 'sg01|1kg' = 1000g. obs e sempre o ultimo campo: para pizza, 'pz04|1|grande|catupiry|pz01|caprichar no queijo'; para os demais, 'hb01|1||||sem cebola'."
          required      = true
        }
      }

      functions {
        name        = "ver_carrinho"
        description = "Mostra os itens ja escolhidos no carrinho, com precos e subtotal. Use quando a pessoa perguntar o que escolheu ou como esta o pedido"
      }

      functions {
        name        = "remover_item"
        description = "Remove um item do carrinho pela posicao numerada mostrada em ver_carrinho (campo 'numero' de cada linha). Use quando a pessoa disser para tirar ou cancelar um item especifico"

        parameters {
          map_block_key = "numero"
          type          = "string"
          description   = "Posicao do item no carrinho (1 = primeiro item), conforme o numero mostrado por ver_carrinho. Ex.: '2' remove o segundo item da lista"
          required      = true
        }
      }

      functions {
        name        = "alterar_quantidade"
        description = "Altera a quantidade (ou, para itens vendidos por kg, os gramas) de um item ja no carrinho, pela posicao numerada mostrada em ver_carrinho. Use quando a pessoa disser para mudar de quantas unidades ou gramas ela quer"

        parameters {
          map_block_key = "numero"
          type          = "string"
          description   = "Posicao do item no carrinho (1 = primeiro item), conforme o numero mostrado por ver_carrinho. Ex.: '1' altera o primeiro item"
          required      = true
        }

        parameters {
          map_block_key = "quantidade"
          type          = "string"
          description   = "Nova quantidade. Para itens normais, um numero de unidades (ex.: '3'). Para itens vendidos por kg (categoria salgados), os gramas (ex.: '500' ou '500g'; '1kg' = 1000g)"
          required      = true
        }
      }

      functions {
        name        = "limpar_carrinho"
        description = "Esvazia o carrinho para recomecar o pedido do zero"
      }

      functions {
        name        = "revisar_pedido"
        description = "Mostra o resumo final do carrinho com frete e total para um CEP, sem registrar. Use para confirmar antes de finalizar"

        parameters {
          map_block_key = "cep"
          type          = "string"
          description   = "CEP de entrega, 8 digitos"
          required      = true
        }
      }

      functions {
        name        = "finalizar_pedido"
        description = "Fecha o pedido: grava o carrinho completo como log estruturado no CloudWatch e gera o numero, que serve de referencia para a loja localizar o pedido nos logs. Nao existe registro consultavel fora desta conversa nem fora da sessao. Chamar somente apos a pessoa confirmar o resumo do revisar_pedido"

        parameters {
          map_block_key = "cep"
          type          = "string"
          description   = "CEP de entrega, 8 digitos"
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

# Acao interna "User Input" (user__askuser). Sem ela, quando o agente precisa
# pedir um dado ao cliente (ex.: o CEP no fechamento), o prompt de orquestracao
# do Bedrock manda perguntar via user__askuser — que nao existe se este action
# group nao for habilitado — e o Nova entra em loop chamando outras funcoes
# (ver_carrinho) em vez de perguntar. Com ela habilitada, ele devolve a
# pergunta ao usuario e a conversa avanca.
resource "aws_bedrockagent_agent_action_group" "user_input" {
  action_group_name             = "UserInputAction"
  agent_id                      = aws_bedrockagent_agent.this.agent_id
  agent_version                 = "DRAFT"
  parent_action_group_signature = "AMAZON.UserInput"
  skip_resource_in_use_check    = true
  prepare_agent                 = true
}

resource "aws_bedrockagent_agent_alias" "dev" {
  agent_alias_name = "dev"
  agent_id         = aws_bedrockagent_agent.this.agent_id
  description      = "Alias de teste"

  depends_on = [
    aws_bedrockagent_agent_action_group.pedidos,
    aws_bedrockagent_agent_action_group.user_input,
  ]
}
