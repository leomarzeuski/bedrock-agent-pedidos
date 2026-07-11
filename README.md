# Bedrock Agent — Agente de Pedidos (estudo)

Agent de pedidos com 1 action group Lambda (`consultar_cardapio`, `validar_cep`, `criar_pedido`), cardápio hardcoded e validação de CEP via ViaCEP.

## Pré-requisito manual (uma vez só)

No console AWS, em **Bedrock → Model access** (us-east-1), habilite o **Claude 3 Haiku**. Sem isso o agent falha na invocação com AccessDenied.

## Deploy

```bash
terraform init
terraform plan
terraform apply
```

## Testar

Opção 1 — console: Bedrock → Agents → agente-pedidos → **Test** (usa o DRAFT, já preparado).

Opção 2 — CLI (usa o alias `dev`):

```bash
terraform output -raw invoke_example
```

Copie e rode o comando retornado. A resposta fica em `resposta.json` (formato de event stream).

## Iterando

- Prompt: edite `instructions.txt` → `terraform apply`
- Lambda: edite `lambda/handler.py` → `terraform apply` (o hash do zip força o update)
- Mudanças no DRAFT aparecem no teste do console na hora. O alias `dev` aponta pra uma versão publicada — pra ele pegar mudanças: `terraform apply -replace=aws_bedrockagent_agent_alias.dev`

## Limpar

```bash
terraform destroy
```

## Custo

Agent parado = R$ 0. Você paga só a inferência do Haiku por invocação (centavos). Lambda dentro do free tier.
