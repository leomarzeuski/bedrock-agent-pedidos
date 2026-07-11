# Bedrock Agent — Agente de Pedidos (estudo)

> 📋 [Avaliação completa do repo (2026-07-11)](docs/avaliacao-2026-07-11.md) — bugs confirmados, gaps para "atendente completo de padaria" e roadmap.

Agente de delivery no Amazon Bedrock: **2 lojas**, **~118 itens** em 11 categorias, pizzas **meio a meio** com borda e tamanho, **combos**, **salgados vendidos por kg** (pedidos em gramas), observações por item e por pedido, horários de funcionamento por loja, janelas de disponibilidade por item e frete por loja. Foundation model **Amazon Nova Pro**; a lógica de negócio roda num action group Lambda em Python (stdlib apenas).

## Arquitetura

Terraform provisiona tudo:

| Arquivo | O que cria |
|---|---|
| `agent.tf` | O agente, o action group e as 9 funções (schema) |
| `iam.tf` | Roles do agente e da Lambda (policy derivada de `var.foundation_model`) |
| `lambda.tf` | Empacota e publica a Lambda do action group |
| `variables.tf` | `region`, `agent_name`, `foundation_model` |
| `outputs.tf` | `agent_id`, `agent_alias_id`, `como_testar` |
| `instructions.txt` | Prompt de sistema do agente |

Lambda modularizada (`lambda/`):

- `handler.py` — dispatch das funções + envelope de resposta do Bedrock
- `dados.py` — as 2 lojas, bordas e categorias; importa o cardápio
- `cardapio_itens.py` — os ~110 itens (gerado)
- `geo.py` — horários, disponibilidade de item, validação de CEP (ViaCEP) e frete
- `pedido.py` — motor de preços: parsing dos itens, validação e precificação
- `carrinho.py` — carrinho na sessão (adicionar/ver/limpar/revisar/finalizar)

### Funções do action group

1. `consultar_cardapio(categoria?, loja?)` — sem categoria, lista as categorias; com categoria, os itens (filtra por loja; aceita id "A"/"B" ou o nome da loja).
2. `listar_lojas()` — as 2 lojas com endereço, horário, se estão abertas agora e frete.
3. `adicionar_itens(itens, loja?)` — adiciona itens ao carrinho e devolve o carrinho com preços, a loja e se ela está aberta. Item idêntico a um já no carrinho soma a quantidade em vez de duplicar linha. Se a loja não for informada, escolhe automaticamente uma loja **aberta** que tenha os itens (e sugere uma loja aberta alternativa se a escolhida estiver fechada).
4. `ver_carrinho()` — mostra o que já foi escolhido, com preços e o número de cada linha.
5. `remover_item(numero)` — remove um item do carrinho pela posição mostrada em `ver_carrinho`.
6. `alterar_quantidade(numero, quantidade)` — altera a quantidade (ou gramas, para itens vendidos por kg) de um item já no carrinho.
7. `limpar_carrinho()` — esvazia o carrinho.
8. `revisar_pedido(cep)` — resumo final com frete e total, **sem registrar**; valida se o CEP está na área de entrega da loja.
9. `finalizar_pedido(cep, nome_cliente, observacoes?)` — revalida o carrinho, grava o pedido como log estruturado no CloudWatch (não é um registro consultável fora da conversa) e gera o número. Chamada de novo com o carrinho já vazio devolve o mesmo pedido (idempotente).

O carrinho fica em `sessionAttributes`, que o Bedrock mantém entre os turnos — a Lambda é a dona dos itens, então nada se perde na conversa. As funções **recusam** com motivo explicado: loja fechada, item fora do horário, item de outra loja, CEP inválido ou fora da área de entrega.

## Modelo

`var.foundation_model = "us.amazon.nova-pro-v1:0"`. Modelo próprio da Amazon, **não exige** o formulário de use case (ao contrário dos Claude, cujo acesso não está liberado nesta conta). Nada a habilitar no console para o Nova. Começou no Nova Lite, mas ele montava mal o parâmetro `itens` e entrava em loop; o Nova Pro é confiável em tool use.

Os itens do pedido usam um formato simples (sem JSON aninhado, que modelos pequenos corrompem): `id|qtd|tamanho|borda|meio_a_meio|obs`, itens separados por `;`. Ex.: `bb05|3 ; pz04|1|grande|catupiry|pz01`.

## Persistência

Este projeto **não usa banco de dados nem fila/notificação externa** (decisão de escopo, não lacuna): todo o estado do pedido vive em `sessionAttributes`, mantido pelo Bedrock durante a conversa — uma sessão nova começa com carrinho vazio. `finalizar_pedido` grava o pedido completo como uma linha de JSON estruturado no CloudWatch Logs (evento `pedido_finalizado`), e o `PED-...` retornado é a referência para achar essa linha nos logs — não é um registro consultável em nenhum sistema, nem sobrevive fora da sessão que o gerou.

## Deploy

```bash
terraform init
terraform apply
```

O alias `dev` aponta para uma **versão publicada**. Depois de mudar cardápio, schema ou instruções, gere uma versão nova e reaponte o alias (gera um `alias_id` novo):

```bash
terraform apply -replace=aws_bedrockagent_agent_alias.dev
```

## Testar (SDK Python)

O AWS CLI não suporta `InvokeAgent` (é streaming), então usa-se o `invoke.py`:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install boto3
AGENT_ID=$(terraform output -raw agent_id) ALIAS_ID=$(terraform output -raw agent_alias_id) python3 invoke.py "quais lojas voces tem?"
```

Ele imprime a `session` no fim; para continuar a mesma conversa, passe-a como 2º argumento:

```bash
AGENT_ID=$(terraform output -raw agent_id) ALIAS_ID=$(terraform output -raw agent_alias_id) python3 invoke.py "quero uma pizza grande meia calabresa meia marguerita" cli-a1b2c3d4
```

## Iterando

- Prompt: edite `instructions.txt` → `apply` + replace do alias
- Lambda: edite os arquivos em `lambda/` → `apply` (o hash do zip força o update) + replace do alias
- Mudanças no DRAFT aparecem no **Test** do console na hora; o alias só pega depois do replace

## Custo

Agente parado = R$ 0. Paga-se só a inferência do Nova Pro por invocação (centavos) e a Lambda fica no free tier.

## Limpar

```bash
terraform destroy
```

## Nota

Se aparecer `dependencyFailedException` (timeout do modelo no Bedrock), é transiente — a própria API pede para repetir, e o `invoke.py` já **retenta** erros desse tipo.
