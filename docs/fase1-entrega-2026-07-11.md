# Fase 1 — entrega (2026-07-11)

Execução completa do plano em [`docs/superpowers/plans/2026-07-11-fase1-atendente-pedidos.md`](superpowers/plans/2026-07-11-fase1-atendente-pedidos.md), via `superpowers:subagent-driven-development` (implementador + revisor independentes por tarefa, mais uma revisão final de branch inteira). Sem banco de dados nem qualquer persistência externa, conforme restrição do plano — "registrar o pedido" é log estruturado no CloudWatch.

## Resultado

- **76/76 testes passando** (`pytest tests/ -v`), cobrindo `pedido.py`, `geo.py`, `carrinho.py`, `handler.py` — zero antes desta fase.
- **9 commits** na sequência `f2fe698..c37220c`: Setup+Task 0, Task 1, Task 2 (2 tentativas — a 1ª caiu por erro de infraestrutura a meio caminho, retomada com sucesso pela 2ª), Task 3 (+1 rodada de correção), Task 4, e uma rodada final de correções pós-revisão de branch inteira.
- Cada tarefa passou por implementador e revisor (spec + qualidade) independentes; 3 das 5 tarefas exigiram uma rodada de correção antes de aprovar. A revisão final de branch inteira (modelo mais capaz, olhando as 7 tarefas juntas) encontrou 1 achado importante (novo, não estava nos 44 originais) e 5 achados menores — todos corrigidos e re-verificados.
- **2 bugs reais no próprio plano** foram encontrados e corrigidos durante a execução: (1) duas asserções de teste tautológicas (`assert X or True`, sempre verdadeiras) no plano original — corrigidas antes de despachar; (2) o código de exemplo de `parse_quantidade` no plano aceitaria `"1.5"` como válido, contradizendo o próprio teste do plano — o implementador corrigiu a implementação, não o teste.
- **1 limite real da AWS descoberto**: a descrição do parâmetro `obs` do plano tinha 641 caracteres; o Bedrock rejeita descrições de parâmetro de action group acima de 500 — corrigido preservando os dois exemplos (pizza e não-pizza) em 472 caracteres.

## Checklist — os 44 findings de `docs/revisao-2026-07-11.findings.json`

Legenda: **corrigido** = implementado como recomendado · **adaptado** = implementado de forma diferente do recomendado (explicado) · **pulei porque X** = fora do escopo desta fase (explicado).

### carrinho-precos (7)

| # | Finding | Status |
|---|---|---|
| 1 | `finalizar_pedido` não registra o pedido em lugar nenhum (crítico) | **corrigido** — Task 0: log JSON estruturado (`print`) capturado pelo CloudWatch antes de esvaziar o carrinho, com `session_attrs["ultimo_pedido"]` para idempotência. Ver também #21, #28 (mesmo achado, 3 dimensões). |
| 2 | Sem remover item/alterar quantidade; duplicatas sem proteção | **corrigido** — Task 1: `remover_item`, `alterar_quantidade`, merge de itens idênticos (soma qtd em vez de duplicar linha). |
| 3 | qtd não numérica vira 1 silenciosamente | **corrigido** — Task 1/2: `pedido.parse_quantidade` retorna erro explícito; aceita sufixo de peso (`"500g"`, `"1kg"`). |
| 4 | Campos fora de ordem / obs com `\|` ou `;` engolidos sem erro | **corrigido** — Task 2: `obs` junta tudo a partir do 5º campo (não trunca em `\|`); campos de pizza em item não-pizza viram observação em vez de sumir. |
| 5 | Loja forçada ignorada silenciosamente com carrinho não-vazio | **corrigido** — Task 2: `adicionar_itens` recusa explicitamente quando a loja forçada diverge da loja do carrinho. |
| 6 | `sucesso=True` junto com erro em `adicionar_itens` | **corrigido** — Task 2: guarda verifica erro do `_resumo` antes de marcar sucesso. |
| 7 | Mensagem de loja fechada afirma falsamente "nenhuma loja aberta tem esse item" | **corrigido** — Task 2: verifica lojas candidatas abertas antes de usar o texto de exclusividade; sugere a loja alternativa aberta. |
| 8 | `finalizar_pedido` não idempotente (2ª chamada = "Carrinho vazio") | **corrigido** — Task 1: retorna o último pedido com `ja_finalizado: true` em vez de erro. |
| 9 | Arredondamento float subcobra centavos no peso | **corrigido** — Task 2: motor de preços inteiro em `Decimal` com `ROUND_HALF_UP`. |

### geo-horarios (8)

| # | Finding | Status |
|---|---|---|
| 10 | Janela cruzando meia-noite nunca abre a loja | **corrigido** — Task 2: `_dentro_da_faixa`/`_cruza_meia_noite` em `geo.py`. Um caso residual (falso-positivo às 00:00 do 1º dia aberto após um dia fechado) foi achado na revisão final de branch inteira e corrigido no commit `c37220c`, com teste de regressão usando os dados reais da loja A. |
| 11 | ViaCEP fora do ar ≡ "CEP não encontrado" (mensagem enganosa) | **corrigido** — Task 2: `_get_json` retorna `(dict, falha)`; 1 retry antes de desistir; mensagem distinta para serviço indisponível. |
| 12 | Sem validação de área de entrega (CEP de Manaus aceito) | **corrigido** — Task 2: `geo.area_atendida` valida cidade/UF contra a loja; `revisar_pedido` recusa fora da área. |
| 13 | `disponivel_agora` usa as outras lojas quando há filtro | **corrigido** — Task 2: `handler.consultar_cardapio` escopa a disponibilidade só à loja filtrada. |
| 14 | `KeyError` se parâmetro do Bedrock vier sem `value` | **corrigido** — Task 2: `p.get("value", "")` + try/except no dispatch. |
| 15 | `item_disponivel` com a mesma limitação de janela overnight | **corrigido** — Task 2: mesma correção de `_dentro_da_faixa` aplicada. |
| 16 | Filtro `loja` inválido retorna cardápio vazio sem erro | **corrigido** — Task 2: `handler._resolver_loja` valida e aceita nome ou id, erro explícito se inválido. |
| 17 | Payload do cardápio cresce linearmente (seguro hoje, ~7 KB) | **pulei porque** não é um bug ativo hoje (medido com folga sobre o limite do Bedrock) e paginação não estava nos quick-wins da Fase 1 — fica de observação para quando o cardápio crescer (Fase 2). |

### bedrock-schema (9)

| # | Finding | Status |
|---|---|---|
| 18 | Categoria "salgados" ausente do enum em `agent.tf` | **corrigido** — Task 3. |
| 19 | Campo `obs` não documentado no schema (perde observação em silêncio) | **corrigido** — Task 3: descrição documenta `obs` com exemplo de pizza e de item comum. **Adaptado**: o texto do plano (641 caracteres) excede o limite real de 500 caracteres do Bedrock para descrição de parâmetro — reescrito em 472 caracteres preservando os dois exemplos (achado + corrigido em 2 rodadas de revisão). |
| 20 | `idle_session_ttl_in_seconds = 600` evapora o carrinho | **corrigido** — Task 3: subiu para 3600s (teto aceito pela API é 5400s). |
| 21 | `finalizar_pedido` — "número do pedido" fictício | **corrigido** — mesmo achado de #1/#28, ver Task 0. |
| 22 | `consultar_cardapio` não valida o parâmetro `loja` | **corrigido** — Task 2, mesmo fix de #16. |
| 23 | `obs_disponibilidade` sem loja/horário no ramo fora-da-janela | **corrigido** — Task 2: o texto agora inclui a loja e o horário mesmo no ramo "fora da janela de horário do item". |
| 24 | Deploy do alias por `-replace` gera `alias_id` novo a cada mudança | **pulei porque** é uma mudança de processo de deploy (não de código), explicitamente listada no plano como fora do escopo das Tarefas 0-4 (roadmap "transversal", item 10). |
| 25 | `sessionAttributes` sem cap de tamanho nem tratamento de estouro | **pulei porque** não estava nos quick-wins da Fase 1 (avaliação original não incluiu isso na lista de correções rápidas); decisão de política (qual o cap, o que fazer no estouro) melhor tomada com o modelo de item genérico da Fase 2. |
| 26 | Prompt de 6,6 KB denso em proibições que o Nova tende a pular | **pulei porque** é uma reengenharia de prompt (julgamento de produto/UX), não um bug mecânico — fora do escopo das Tarefas 0-4. |
| 27 | README contradiz a si mesmo (Nova Lite vs Pro; 5 vs 7 funções) | **corrigido** — Task 3: Nova Pro, contagem de funções atualizada para 9 (7 originais + `remover_item`/`alterar_quantidade`). Mesmo achado de #43. |

### gap-padaria (10)

| # | Finding | Status |
|---|---|---|
| 28 | Pedido não persiste (a loja nunca sabe) | **corrigido** — mesmo achado de #1, ver Task 0. |
| 29 | Cardápio/preços/lojas hardcoded em `.py` (mudar preço = redeploy) | **pulei porque Fase 2** — catálogo em DynamoDB é item explícito do roadmap de Fase 2; proibido adicionar banco nesta fase. |
| 30 | Sem busca de item por nome (`buscar_item`) | **pulei porque Fase 2** — item explícito do roadmap. |
| 31 | Peculiaridades hardcoded para pizza (sem modificadores genéricos) | **pulei porque Fase 2** — "modificadores genéricos de item" é item explícito do roadmap, e precisa vir antes de cadastrar itens novos (ordem do roadmap). |
| 32 | Carrinho sem remover/alterar E morre com a sessão (TTL) | **adaptado/parcial** — a parte "sem remover/alterar" foi **corrigida** (Task 1) e o TTL subiu de 600s→3600s (Task 3) como paliativo; a causa raiz ("morre com a sessão") continua por design nesta fase — persistir o carrinho fora da sessão (ex.: DynamoDB por telefone) é Fase 2, proibido nesta fase. |
| 33 | Sem identidade de cliente nem canal real (só `invoke.py` de teste) | **pulei porque Fase 3** — canal WhatsApp + identidade por telefone é item explícito do roadmap de Fase 3. |
| 34 | Multi-loja é "2 lojas fixas A/B" cravadas no schema/prompt | **pulei porque Fase 2** — lojas dinâmicas em DynamoDB (com exceções de calendário) é item explícito do roadmap; Fase 1 só corrigiu os bugs *dentro* do modelo atual de 2 lojas (janela overnight, área de entrega, etc.), não generalizou o modelo. |
| 35 | Sem pagamento nem ciclo de status do pedido | **pulei porque Fase 3** — itens explícitos do roadmap. |
| 36 | Sem noção de estoque/esgotado | **pulei porque Fase 2** — flag `esgotado` por item é item explícito do roadmap (junto do catálogo dinâmico). |
| 37 | Entrega sem área/raio e sem ETA; ViaCEP como ponto único de falha | **adaptado/parcial** — validação de área de entrega (cidade/UF) foi **corrigida** (Task 2, `area_atendida`) e a resiliência do ViaCEP melhorou (retry + distinção de falha, Task 2); raio/distância e ETA via Amazon Location continuam Fase 2 (proibido adicionar integração nova nesta fase). |
| 38 | Zero testes no motor de preços; observabilidade limitada | **corrigido** — 76 testes pytest cobrindo `pedido.py`/`geo.py`/`carrinho.py`/`handler.py` (Tasks 0-4); logging estruturado no fechamento do pedido (Task 0). |
| 39 | Prompt/categorias duplicados em 3 lugares (dados, prompt, schema) | **pulei porque** gerar a lista de categorias a partir de `dados.CATEGORIAS` via Terraform exigiria uma fonte de dados externa (`external` data source chamando Python) — conta como recurso novo, fora do escopo desta fase (nota deixada na própria Task 3 para revisitar se o cardápio crescer). |

### infra-terraform (5)

| # | Finding | Status |
|---|---|---|
| 40 | `archive_file` empacota `__pycache__` no zip da Lambda | **corrigido** — Task 3: `excludes = ["__pycache__", "**/*.pyc"]`. |
| 41 | Estado Terraform local, sem backend remoto nem lock | **pulei porque** é infraestrutura de colaboração (S3 + lock), explicitamente fora do escopo das Tarefas 0-4 pelo próprio texto do plano ("nada de backend remoto"). |
| 42 | `invoke.py` com `agent_id`/`alias_id` hardcoded, região fixa | **corrigido** — Task 3: reescrito sem defaults (falha com mensagem clara se as env vars não estiverem definidas), região via `AWS_REGION`. Um bug irmão foi achado na revisão final: `outputs.tf`'s `como_testar` tinha o mesmo problema (não setava `AGENT_ID`) — **corrigido** no commit final `c37220c`. |
| 43 | README contradiz `variables.tf` (Nova Lite vs Pro) | **corrigido** — mesmo achado de #27, Task 3. |
| 44 | Policy do agente só normaliza o prefixo `us.` do inference profile | **pulei porque** é uma mudança de infraestrutura (IAM policy) fora do escopo explícito das Tarefas 0-4; nenhuma loja/modelo desta fase usa `eu.`/`apac.`, então é um risco latente, não ativo. |

## Achado novo (fora dos 44 originais)

A revisão final de branch inteira encontrou 1 caso residual na correção da janela overnight (finding #10): a loja ficava incorretamente "aberta" às 00:00 do primeiro dia de funcionamento após um dia fechado (ex.: terça 00:00, com segunda fechada) — a lógica confundia essa hora com a cauda legítima da janela do dia anterior. Corrigido no commit final (`c37220c`) com teste de regressão usando os dados reais da loja A, sem regredir nenhum dos casos já cobertos (fronteiras 23:59/00:00, janela genuinamente overnight).

## O que fica para a Fase 2 e Fase 3

**Fase 2** — catálogo e lojas em DynamoDB (com exceções de calendário e flag `esgotado`) + cache na Lambda; `buscar_item(texto)`; modificadores genéricos de item (antes de cadastrar itens de padaria, para não cadastrar no modelo errado); raio de entrega/ETA via Amazon Location.

**Fase 3** — canal WhatsApp (webhook → `invoke_agent` com `sessionId` = telefone) + tabela de clientes; status do pedido (recebido → preparo → saiu → entregue); pagamento (forma + troco primeiro, Pix depois).

**Transversal, fora de qualquer fase específica** (achados de infra que não bloqueiam produto): backend remoto do Terraform (S3 + lock), deploy do alias sem `-replace`, `iam.tf` trimprefix para `eu.`/`apac.`, cap de tamanho do carrinho em `sessionAttributes`, geração da lista de categorias do `agent.tf` a partir de `dados.CATEGORIAS`.
