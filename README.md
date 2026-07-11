# Bedrock Agent — Agente de Pedidos (estudo)

Agente de delivery no Amazon Bedrock: **2 lojas**, **~110 itens** em 10 categorias, pizzas **meio a meio** com borda e tamanho, **combos**, observações por item e por pedido, horários de funcionamento por loja, janelas de disponibilidade por item e frete por loja. Foundation model **Amazon Nova Lite**; a lógica de negócio roda num action group Lambda em Python (stdlib apenas).

## Arquitetura

Terraform provisiona tudo:

| Arquivo | O que cria |
|---|---|
| `agent.tf` | O agente, o action group e as 5 funções (schema) |
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
- `pedido.py` — validação e precificação; `cotar_pedido` (dry-run) e `criar_pedido`

### Funções do action group

1. `consultar_cardapio(categoria?, loja?)` — sem categoria, lista as categorias; com categoria, os itens (filtra por loja).
2. `listar_lojas()` — as 2 lojas com endereço, horário, se estão abertas agora e frete.
3. `validar_cep(cep)` — valida e retorna o endereço (ViaCEP).
4. `cotar_pedido(loja, itens, cep, observacoes?)` — calcula itens/subtotal/frete/total **sem registrar** (é o que monta o resumo).
5. `criar_pedido(loja, itens, cep, nome_cliente, observacoes?)` — revalida e registra, gerando o número.

`criar_pedido`/`cotar_pedido` **recusam** com motivo explicado: loja fechada, item fora do horário, item de outra loja, ou CEP inválido.

## Modelo

`var.foundation_model = "us.amazon.nova-pro-v1:0"`. Modelo próprio da Amazon, **não exige** o formulário de use case (ao contrário dos Claude, cujo acesso não está liberado nesta conta). Nada a habilitar no console para o Nova. Começou no Nova Lite, mas ele montava mal o parâmetro `itens` e entrava em loop; o Nova Pro é confiável em tool use.

Os itens do pedido usam um formato simples (sem JSON aninhado, que modelos pequenos corrompem): `id|qtd|tamanho|borda|meio_a_meio|obs`, itens separados por `;`. Ex.: `bb05|3 ; pz04|1|grande|catupiry|pz01`.

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
ALIAS_ID=$(terraform output -raw agent_alias_id) python3 invoke.py "quais lojas voces tem?"
```

Ele imprime a `session` no fim; para continuar a mesma conversa, passe-a como 2º argumento:

```bash
ALIAS_ID=$(terraform output -raw agent_alias_id) python3 invoke.py "quero uma pizza grande meia calabresa meia marguerita" cli-a1b2c3d4
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
