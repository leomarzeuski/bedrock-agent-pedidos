# Design — API HTTP para o agente (Lambda Function URL)

> Status: aprovado no brainstorming em 2026-07-14. Próximo passo: plano de implementação.

## Objetivo

Expor o agente Bedrock (Nova Pro) como uma **API HTTP** consumível por qualquer
cliente (curl, frontend, Postman), sem que ninguém precise rodar o `invoke.py`
localmente nem ter credenciais AWS. Uma chamada HTTP com uma mensagem devolve a
resposta do agente e mantém a conversa (carrinho/contexto) entre chamadas.

Nada muda no agente, nas tools (Lambda de negócio) nem no Terraform existente.
Isto é uma **camada nova por cima**.

## Arquitetura

Uma **segunda Lambda** ("wrapper"), separada da Lambda de negócio:

- A Lambda de negócio (`agente-pedidos-actions`) é chamada *pelo* Bedrock — são as tools.
- A wrapper (`agente-pedidos-api`) é um *cliente* do agente — chama
  `bedrock-agent-runtime.invoke_agent`, exatamente como o `invoke.py` faz hoje.

Papéis IAM, permissões e deploy ficam independentes entre as duas.

```
cliente ──HTTPS + x-api-key──> Function URL ──> Lambda wrapper ──invoke_agent──> Agente (Nova Pro) ──> Lambda de negócio (tools)
                                                (concatena chunks, retenta transientes)
```

Sem servidor para manter: R$0 parada, paga-se só a inferência do Nova Pro por
chamada — igual ao resto do repo.

## Contrato da API

Um único caminho, roteado pelo método HTTP:

| Método | Ação | Request | Response 200 |
|---|---|---|---|
| `POST /` | Conversa com o agente | `{ "mensagem": "...", "session": "opcional" }` | `{ "resposta": "<texto do agente>", "session": "api-xxxx" }` |
| `GET /` | Health check (sem auth, **não chama o agente**) | — | `{ "ok": true }` |

- Sem `session` no request, a wrapper gera uma (`api-<8 hex>`) e a devolve. O
  cliente reenvia esse valor nas próximas chamadas para manter o carrinho/contexto
  (é o mesmo `sessionId` que o Bedrock já usa entre turnos).
- `resposta` é o texto natural do agente — o mesmo que o `invoke.py` imprime.

### Erros

| Código | Quando | Corpo |
|---|---|---|
| `400` | Body não é JSON, ou `mensagem` ausente/vazia | `{ "erro": "..." }` |
| `401` | Header `x-api-key` ausente ou diferente do segredo | `{ "erro": "unauthorized" }` |
| `405` | Método diferente de GET/POST | `{ "erro": "..." }` |
| `500` | Falha inesperada (detalhe completo vai só para o CloudWatch) | `{ "erro": "..." }` |

## Auth

- Function URL com `authorization_type = "NONE"` (URL pública), mas a wrapper
  **exige** o header `x-api-key: <segredo>` e recusa com `401` sem ele.
  Comparação com `hmac.compare_digest` (constant-time).
- A chave é **gerada pelo Terraform** via `random_password` e lida por
  `terraform output -raw api_key` — nenhum segredo vai para o git.
- Override opcional: `var.api_key` (sensível); se definida, substitui a gerada.
- CORS habilitado na Function URL (`allow_headers: content-type, x-api-key`;
  `allow_methods: GET, POST`; `allow_origins: *`) para um frontend poder chamar.
  A gate real de acesso é a chave, não o CORS.

## Robustez

A wrapper herda a lógica do `invoke.py`:

- Concatena os `chunk`s do stream de `completion` numa string única.
- **Retenta** (até 3 tentativas, backoff 2s/4s) os erros transientes do Bedrock:
  `dependencyFailedException`, `throttlingException`, `modelTimeout`.
- Cliente boto3 com `read_timeout=120`; `timeout` da Lambda em **120s** (um turno
  pode encadear várias tools: CEP, cotação, pedido).
- Zero dependências no zip — `boto3` vem do runtime da Lambda (python3.12),
  mantendo o "stdlib apenas" do projeto.

## Componentes

### `api/handler.py` (novo)

- Lê env `AGENT_ID`, `ALIAS_ID`, `API_KEY` em tempo de chamada (facilita teste).
- Cliente boto3 `bedrock-agent-runtime` criado de forma preguiçosa/injetável, para
  os testes conseguirem substituí-lo sem rede.
- `lambda_handler(event, context)`:
  1. `GET` → `200 {"ok": true}` (sem auth, sem chamar o agente).
  2. Método ≠ `POST` → `405`.
  3. Valida `x-api-key` (constant-time) → `401` se falhar.
  4. Faz parse do body (decodifica base64 se `isBase64Encoded`); `mensagem`
     obrigatória e não vazia → senão `400`.
  5. `session = body.get("session") or "api-<8 hex>"`.
  6. Chama `invoke_agent`, concatena chunks, com o loop de retry de transientes.
  7. `200 {"resposta": ..., "session": ...}`.
  8. Qualquer exceção inesperada → `500` (mensagem curta; detalhe no CloudWatch).

### Terraform

| Arquivo | Mudança |
|---|---|
| `api.tf` (novo) | `archive_file` de `api/`; `aws_lambda_function.api` (timeout 120, env AGENT_ID/ALIAS_ID/API_KEY); `aws_lambda_function_url.api` (`NONE` + bloco `cors`); `aws_lambda_permission.api_url_public` (`lambda:InvokeFunctionUrl`, principal `*`, `function_url_auth_type = NONE`); `random_password.api_key`; `local.api_key = coalesce(var.api_key, random_password.api_key.result)` |
| `iam.tf` | + `aws_iam_role.api`; attachment de `AWSLambdaBasicExecutionRole`; `aws_iam_role_policy` com `bedrock:InvokeAgent` no `aws_bedrockagent_agent_alias.dev.agent_alias_arn` |
| `versions.tf` | + provider `hashicorp/random` (`>= 3.5`) |
| `variables.tf` | + `api_key` (string, `default = null`, `sensitive = true`) |
| `outputs.tf` | + `api_url` (Function URL); `api_key` (sensível); `como_testar_api` (curl com `$(terraform output -raw ...)`, sem embutir o segredo) |

### `tests/test_api.py` (novo)

Offline (sem rede, sem AWS, sem inferência — R$0), no estilo dos testes atuais.
Substitui o cliente boto3 por um fake cujo `invoke_agent` devolve um `completion`
com chunks fixos. Casos:

- `GET` health → `200 {"ok": true}` sem chave.
- `POST` sem chave / com chave errada → `401`.
- `POST` body inválido (não-JSON ou sem `mensagem`) → `400`.
- Método não suportado → `405`.
- `POST` OK sem `session` → `200`, `resposta` concatenada, `session` gerada.
- `POST` OK com `session` → devolve a mesma `session`.
- Erro transiente na 1ª tentativa e sucesso na 2ª → `200` (prova o retry).

### `README.md`

Nova seção "API HTTP (Lambda Function URL)": como obter URL e chave dos outputs,
exemplo de `curl` (POST e health) e como reusar a `session`.

## Plano de teste — barato de propósito

1. **Offline (R$0):** `terraform plan` (valida a config) + `pytest tests/test_api.py`
   com o boto3 mockado — prova auth, parsing, health, concatenação, `session` e
   retry, **sem tocar na AWS nem gastar inferência**.
2. **Deploy + fumaça (gated no OK do usuário):** `terraform apply` (altera a conta
   AWS) e **uma única** chamada `curl` real (centavos) para confirmar o caminho
   ponta-a-ponta. Sem dezenas de chamadas.

## Fora de escopo (v1)

- Streaming da resposta (SSE) — o retorno é o texto completo, buffered.
- Traces / tool-calls no retorno (debug).
- Resposta estruturada do pedido (JSON do carrinho) — o retorno é o texto do agente.

Todos podem ser adicionados depois sem retrabalho da base.
