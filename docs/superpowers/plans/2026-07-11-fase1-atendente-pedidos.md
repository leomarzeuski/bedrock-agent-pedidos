# Fase 1 — Atendente de Pedidos (crítico + quick wins + testes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os achados críticos e os quick wins da Fase 1 do roadmap em `docs/avaliacao-2026-07-11.md` — pedido finalizado passa a deixar rastro em CloudWatch Logs, o carrinho fica editável (remover/alterar/mesclar/idempotente), uma dúzia de bugs de parsing/preço/horário/CEP/dispatch são corrigidos, o schema e a documentação passam a bater com o comportamento real, e uma suite pytest cobre tudo isso — sem adicionar nenhuma persistência externa (banco, fila, notificação).

**Architecture:** Nenhuma peça nova de infraestrutura. O carrinho continua 100% em `sessionAttributes`; "persistir o pedido" vira um `print(json.dumps(...))` estruturado no handler da Lambda (linha de log, não linha de banco) mais uma cópia do último pedido em `sessionAttributes["ultimo_pedido"]` só para a idempotência dentro da mesma sessão. Os módulos afetados são os mesmos cinco arquivos Python da Lambda (`pedido.py`, `geo.py`, `carrinho.py`, `handler.py`, `dados.py`), o schema Terraform (`agent.tf`, `lambda.tf`), o cliente de teste (`invoke.py`) e a documentação (`README.md`, `instructions.txt`).

**Tech Stack:** Python 3.12 stdlib apenas (a Lambda não pode ter dependências de terceiros), pytest para os testes, Terraform + provider `hashicorp/archive` 2.8.0 para o empacotamento.

## Global Constraints

- **Proibido banco de dados ou qualquer persistência externa** (DynamoDB, RDS, S3, SQS, SNS, EventBridge...). Todo estado vive em `sessionAttributes`; "registrar o pedido" = log estruturado no CloudWatch via `print(json.dumps(...))`.
- **Não implementar as Fases 2 e 3** do roadmap (catálogo dinâmico, `buscar_item`, modificadores genéricos, canal WhatsApp, status de pedido, pagamento). Se um achado da avaliação pede uma dessas coisas, ele fica de fora — anotar no checklist final.
- **Não adicionar recursos novos no Terraform** além dos que as tarefas abaixo pedem explicitamente (nada de backend remoto, nada de fila, nada de tabela).
- **Nunca rodar `terraform apply`** durante a execução deste plano — só `terraform validate`/`terraform fmt -check` (somente leitura). Perguntar ao usuário antes de qualquer apply.
- **Estilo do repo:** identificadores em PT-BR sem acento; mensagens de erro amigáveis (são lidas pelo modelo e repassadas ao cliente, então precisam ser claras e completas); stdlib puro (sem pip install na Lambda).
- **Um commit por Tarefa (Task 0–4), não por step.** Isso é uma exceção deliberada ao padrão usual de "um commit por step" da skill de planos — o usuário pediu explicitamente 5 commits atômicos, um por Tarefa, mensagem em português. Todos os steps de uma Task acontecem antes do commit único daquela Task.
- **Rodar a suite pytest inteira ao final de cada Task** (`./.venv/bin/python -m pytest tests/ -v` a partir da raiz do repo) antes do commit daquela Task — não só os testes novos.
- Os testes não podem depender de rede nem de AWS: toda chamada a `geo.consultar_cep`/`geo._get_json` é mockada com `monkeypatch`; todo teste que depende do horário atual injeta um `momento`/`geo.agora` fixo.

---

## Setup (antes da Task 0)

Sem isso nenhum teste roda. Faz parte do mesmo commit da Task 0 (não é uma Task própria).

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`

- [ ] **Step 1: Criar `requirements-dev.txt`**

```
pytest>=8.0,<9
```

- [ ] **Step 2: Instalar no venv já existente**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/pip install -r requirements-dev.txt`
Expected: instala `pytest` (e `iniconfig`/`pluggy`/`packaging` como dependências) sem erro.

- [ ] **Step 3: Criar `pytest.ini`**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 4: Criar `tests/conftest.py`**

```python
"""Config comum dos testes: poe lambda/ no sys.path (os modulos de la usam
import direto, sem pacote) e mocks de rede para geo.consultar_cep."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import geo  # noqa: E402


def mock_cep_valido(monkeypatch, cidade="Sao Paulo", uf="SP", cep="01310100"):
    """Faz geo.consultar_cep responder com um endereco valido, sem rede."""
    resposta = {"logradouro": "Rua Teste", "bairro": "Centro", "localidade": cidade,
                "uf": uf, "cep": cep}
    monkeypatch.setattr(geo, "_get_json", lambda url, timeout=5: resposta)
```

- [ ] **Step 5: Rodar a suite (ainda vazia) para confirmar que a coleta funciona**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/ -v`
Expected: `no tests ran` (ou `collected 0 items`), sem erro de import.

---

### Task 0: Registrar o pedido finalizado (o crítico) + honestidade nas interfaces

`finalizar_pedido` hoje gera um `PED-xxxxxxxx` cosmético e apaga o carrinho sem deixar rastro em lugar nenhum — a loja nunca fica sabendo que o pedido existiu. Sem banco, o mínimo viável é: logar o pedido completo como uma linha de JSON estruturado no CloudWatch (a Lambda já loga `print()` por padrão via CloudWatch Logs) antes de esvaziar o carrinho, guardar uma cópia em `session_attrs["ultimo_pedido"]` (usada pela idempotência da Task 1) e parar de prometer nas interfaces (schema + README) um "registro" que não existe fora da sessão.

**Files:**
- Modify: `lambda/carrinho.py:180-193` (`finalizar_pedido`)
- Modify: `agent.tf` (descrição da função `finalizar_pedido`)
- Modify: `README.md` (item 7 da lista de funções)
- Test: `tests/test_carrinho.py` (novo arquivo)

**Interfaces:**
- Produces: `carrinho.CHAVE_ULTIMO_PEDIDO = "ultimo_pedido"` (constante, chave de sessão) — a Task 1 lê essa chave para a idempotência.
- Produces: `finalizar_pedido(params, session_attrs)` continua devolvendo o mesmo dict de antes (mesmas chaves: `sucesso, loja, endereco_entrega, itens, subtotal, frete, frete_gratis, total, pedido_id, cliente, observacoes?`), sem novas chaves nesta Task.

- [ ] **Step 1: Escrever o teste de log estruturado (vai falhar — a função ainda não loga nada)**

```python
# tests/test_carrinho.py
"""Testes do carrinho: adicionar/ver/remover/alterar/limpar/revisar/finalizar."""

import json
from datetime import datetime

import carrinho
import geo

from conftest import mock_cep_valido

MOMENTO_ABERTO = datetime(2026, 7, 14, 20, 0, tzinfo=geo.TZ)  # terca, A e B abertas


def _carrinho_com_pizza(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    resultado = carrinho.adicionar_itens({"itens": "pz01|1|media"}, session_attrs)
    assert resultado["sucesso"] is True
    return session_attrs


def test_finalizar_pedido_loga_evento_estruturado(monkeypatch, capsys):
    mock_cep_valido(monkeypatch)
    session_attrs = _carrinho_com_pizza(monkeypatch)

    resultado = carrinho.finalizar_pedido(
        {"cep": "01310100", "nome_cliente": "Ana"}, session_attrs)

    assert resultado["sucesso"] is True
    assert resultado["pedido_id"].startswith("PED-")

    saida = capsys.readouterr().out.strip().splitlines()
    linha = json.loads(saida[-1])
    assert linha["evento"] == "pedido_finalizado"
    assert linha["pedido_id"] == resultado["pedido_id"]
    assert linha["cliente"] == "Ana"
    assert linha["total"] == resultado["total"]
    assert linha["loja"] == resultado["loja"]


def test_finalizar_pedido_guarda_ultimo_pedido_na_sessao_e_esvazia_carrinho(monkeypatch):
    mock_cep_valido(monkeypatch)
    session_attrs = _carrinho_com_pizza(monkeypatch)

    resultado = carrinho.finalizar_pedido(
        {"cep": "01310100", "nome_cliente": "Ana"}, session_attrs)

    assert carrinho.CHAVE not in session_attrs
    assert carrinho.CHAVE_ULTIMO_PEDIDO in session_attrs
    salvo = json.loads(session_attrs[carrinho.CHAVE_ULTIMO_PEDIDO])
    assert salvo["pedido_id"] == resultado["pedido_id"]
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_carrinho.py -v`
Expected: `AttributeError: module 'carrinho' has no attribute 'CHAVE_ULTIMO_PEDIDO'` (ou o teste do log falhando por não haver nenhuma linha JSON impressa).

- [ ] **Step 3: Reescrever `finalizar_pedido` em `lambda/carrinho.py`**

Adicionar a constante logo abaixo de `CHAVE = "carrinho"` (linha 15):

```python
CHAVE = "carrinho"
CHAVE_ULTIMO_PEDIDO = "ultimo_pedido"
```

Substituir a função inteira (linhas 180-193):

```python
def finalizar_pedido(params, session_attrs):
    """Revalida o carrinho, registra o pedido no log e esvazia o carrinho.

    Sem banco de dados: "registrar" e gravar o pedido completo como uma linha
    de JSON estruturado no CloudWatch Logs (evento pedido_finalizado). O
    numero PED-... e so uma referencia para achar essa linha nos logs — nao e
    um registro consultavel em nenhum sistema, nem sobrevive fora da sessao.
    """
    resultado = revisar_pedido(params, session_attrs)
    if not resultado.get("sucesso"):
        return resultado

    pedido_id = f"PED-{uuid.uuid4().hex[:8].upper()}"
    resultado["pedido_id"] = pedido_id
    resultado["cliente"] = params.get("nome_cliente")
    obs = (params.get("observacoes") or "").strip()
    if obs:
        resultado["observacoes"] = obs

    print(json.dumps({
        "evento": "pedido_finalizado",
        "pedido_id": pedido_id,
        "loja": resultado["loja"],
        "itens": resultado["itens"],
        "endereco": resultado["endereco_entrega"],
        "total": resultado["total"],
        "cliente": resultado["cliente"],
        "timestamp": geo.agora().isoformat(),
    }, ensure_ascii=False))

    session_attrs[CHAVE_ULTIMO_PEDIDO] = json.dumps(resultado, ensure_ascii=False)
    session_attrs.pop(CHAVE, None)
    return resultado
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_carrinho.py -v`
Expected: 2 passed.

- [ ] **Step 5: Ajustar a descrição de `finalizar_pedido` em `agent.tf`**

Old:
```hcl
      functions {
        name        = "finalizar_pedido"
        description = "Registra o pedido a partir do carrinho e gera o numero. Chamar somente apos a pessoa confirmar o resumo do revisar_pedido"
```

New:
```hcl
      functions {
        name        = "finalizar_pedido"
        description = "Fecha o pedido: grava o carrinho completo como log estruturado no CloudWatch e gera o numero, que serve de referencia para a loja localizar o pedido nos logs. Nao existe registro consultavel fora desta conversa nem fora da sessao. Chamar somente apos a pessoa confirmar o resumo do revisar_pedido"
```

- [ ] **Step 6: Ajustar o item 7 da lista de funções em `README.md`**

Old:
```
7. `finalizar_pedido(cep, nome_cliente, observacoes?)` — revalida e registra, gerando o número.
```

New:
```
7. `finalizar_pedido(cep, nome_cliente, observacoes?)` — revalida o carrinho, grava o pedido como log estruturado no CloudWatch (não é um registro consultável fora da conversa) e gera o número.
```

- [ ] **Step 7: `terraform validate` (somente leitura, não aplica nada)**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 8: Rodar a suite inteira**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/ -v`
Expected: todos passam.

- [ ] **Step 9: Commit**

```bash
git add lambda/carrinho.py agent.tf README.md requirements-dev.txt pytest.ini tests/
git commit -m "$(cat <<'EOF'
fix: registrar pedido finalizado como log estruturado no CloudWatch

finalizar_pedido nao persistia o pedido em lugar nenhum (achado critico da
avaliacao 2026-07-11): o numero PED-... era cosmetico e a loja nunca ficava
sabendo do pedido. Sem banco de dados (restricao de arquitetura do projeto),
o registro minimo e uma linha de JSON estruturado no CloudWatch Logs antes de
esvaziar o carrinho, mais uma copia em session_attrs["ultimo_pedido"] (usada
pela idempotencia da proxima tarefa). Ajusta agent.tf e README para nao
prometer um registro consultavel que nao existe.
EOF
)"
```

---

### Task 1: Carrinho utilizável — remover, alterar, mesclar, idempotência

Hoje o carrinho só cresce: não dá para remover um item nem mudar a quantidade, item idêntico duplica linha em vez de somar, e um retry de `finalizar_pedido` (comum no Nova) devolve "Carrinho vazio" em vez do pedido que acabou de ser fechado.

**Files:**
- Modify: `lambda/pedido.py` (nova função `parse_quantidade`)
- Modify: `lambda/carrinho.py` (`remover_item`, `alterar_quantidade`, merge de itens idênticos, numeração de linha, idempotência de `finalizar_pedido`)
- Modify: `lambda/handler.py` (dispatch das 2 funções novas)
- Modify: `agent.tf` (schema das 2 funções novas)
- Modify: `instructions.txt` (1 linha)
- Test: `tests/test_pedido.py` (novo arquivo), `tests/test_carrinho.py` (estende)

**Interfaces:**
- Consumes (de Task 0): `carrinho.CHAVE_ULTIMO_PEDIDO`, `carrinho.CHAVE`.
- Produces: `pedido.parse_quantidade(texto) -> (valor: int|None, erro: str|None)`. `valor` é sempre um inteiro > 0 quando `erro is None`. Aceita número puro (`"3"`) e peso com sufixo (`"500g"`, `"1kg"` → 1000, aceita vírgula decimal). A Task 2 vai consumir essa mesma função dentro de `pedido.parse_itens`.
- Produces: `carrinho.remover_item(params, session_attrs)` e `carrinho.alterar_quantidade(params, session_attrs)`, mesmo formato de retorno de `adicionar_itens` (dict com `sucesso` + o resumo do carrinho, ou `sucesso=False` + `erro`).
- Produces: cada linha do dict devolvido por `ver_carrinho`/`adicionar_itens`/`remover_item`/`alterar_quantidade` ganha a chave `"numero"` (posição 1-based) — é o que o modelo usa para referenciar o item nas duas funções novas.

- [ ] **Step 1: Escrever os testes de `parse_quantidade` (vão falhar — a função não existe)**

```python
# tests/test_pedido.py
"""Testes do motor de precos: parse_quantidade, parse_itens, precificar."""

import pytest

import pedido


@pytest.mark.parametrize("texto,esperado", [
    ("3", 3),
    ("1", 1),
    ("500", 500),
    ("500g", 500),
    ("1kg", 1000),
    ("1,5kg", 1500),
    ("2KG", 2000),
])
def test_parse_quantidade_valores_validos(texto, esperado):
    valor, erro = pedido.parse_quantidade(texto)
    assert erro is None
    assert valor == esperado


@pytest.mark.parametrize("texto", ["duas", "2x", "1.5", "-2", "0", "", None, "abckg"])
def test_parse_quantidade_valores_invalidos_dao_erro_explicito(texto):
    valor, erro = pedido.parse_quantidade(texto)
    assert valor is None
    assert erro is not None
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_pedido.py -v`
Expected: `AttributeError: module 'pedido' has no attribute 'parse_quantidade'`.

- [ ] **Step 3: Adicionar `parse_quantidade` em `lambda/pedido.py`** (logo abaixo dos imports, antes de `parse_itens`)

```python
def parse_quantidade(texto):
    """Converte o texto de uma quantidade num inteiro positivo.

    Aceita numero puro (unidades ou, para itens por peso, gramas: "3", "500")
    ou peso com sufixo ("500g", "1kg" -> 1000g; aceita virgula decimal:
    "1,5kg" -> 1500g). Retorna (valor, erro): erro e None se valido, e nesse
    caso valor e sempre um inteiro > 0; caso contrario valor e None.
    """
    bruto = str(texto if texto is not None else "").strip().lower().replace(",", ".")
    if not bruto:
        return None, "Quantidade nao informada"

    if bruto.endswith("kg"):
        numero, fator = bruto[:-2].strip(), 1000
    elif bruto.endswith("g"):
        numero, fator = bruto[:-1].strip(), 1
    else:
        numero, fator = bruto, 1

    try:
        valor = round(float(numero) * fator)
    except ValueError:
        return None, f"Quantidade invalida: '{texto}'. Informe um numero, ex.: '2' ou, para itens por peso, '500g'"

    if valor <= 0:
        return None, f"Quantidade deve ser maior que zero: '{texto}'"
    return valor, None
```

- [ ] **Step 4: Rodar para confirmar que passam**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_pedido.py -v`
Expected: todos passam.

- [ ] **Step 5: Escrever os testes de carrinho (remover/alterar/mesclar/idempotência) — vão falhar**

Adicionar em `tests/test_carrinho.py`:

```python
def test_ver_carrinho_numera_as_linhas(monkeypatch):
    session_attrs = _carrinho_com_pizza(monkeypatch)
    resultado = carrinho.ver_carrinho(session_attrs)
    assert resultado["itens"][0]["numero"] == 1


def test_adicionar_item_identico_soma_quantidade_em_vez_de_duplicar(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|2"}, session_attrs)
    resultado = carrinho.adicionar_itens({"itens": "hb01|3"}, session_attrs)

    assert resultado["sucesso"] is True
    assert len(resultado["itens"]) == 1
    assert resultado["itens"][0]["qtd"] == 5


def test_adicionar_itens_diferentes_nao_mescla(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|2"}, session_attrs)
    resultado = carrinho.adicionar_itens({"itens": "bb01|1"}, session_attrs)

    assert len(resultado["itens"]) == 2


def test_remover_item_por_posicao(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|2 ; bb01|1"}, session_attrs)

    resultado = carrinho.remover_item({"numero": 2}, session_attrs)

    assert resultado["sucesso"] is True
    assert len(resultado["itens"]) == 1
    assert resultado["itens"][0]["item"] == "Classico da Casa"  # so restou o hamburguer (bb01 foi removido)


def test_remover_numero_invalido_da_erro(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|2"}, session_attrs)

    resultado = carrinho.remover_item({"numero": 9}, session_attrs)
    assert resultado["sucesso"] is False


def test_remover_carrinho_vazio_da_erro():
    resultado = carrinho.remover_item({"numero": 1}, {})
    assert resultado["sucesso"] is False


def test_remover_ultimo_item_esvazia_o_carrinho(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|2"}, session_attrs)

    resultado = carrinho.remover_item({"numero": 1}, session_attrs)

    assert resultado["sucesso"] is True
    assert carrinho.CHAVE not in session_attrs


def test_alterar_quantidade_por_posicao(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|2"}, session_attrs)

    resultado = carrinho.alterar_quantidade({"numero": 1, "quantidade": "5"}, session_attrs)

    assert resultado["sucesso"] is True
    assert resultado["itens"][0]["qtd"] == 5


def test_alterar_quantidade_invalida_da_erro(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|2"}, session_attrs)

    resultado = carrinho.alterar_quantidade({"numero": 1, "quantidade": "zero"}, session_attrs)
    assert resultado["sucesso"] is False


def test_finalizar_pedido_chamado_2x_e_idempotente(monkeypatch, capsys):
    mock_cep_valido(monkeypatch)
    session_attrs = _carrinho_com_pizza(monkeypatch)

    primeiro = carrinho.finalizar_pedido(
        {"cep": "01310100", "nome_cliente": "Bia"}, session_attrs)
    assert "ja_finalizado" not in primeiro
    capsys.readouterr()  # limpa o log do primeiro finalizar

    segundo = carrinho.finalizar_pedido(
        {"cep": "01310100", "nome_cliente": "Bia"}, session_attrs)

    assert segundo["sucesso"] is True
    assert segundo["ja_finalizado"] is True
    assert segundo["pedido_id"] == primeiro["pedido_id"]
    assert capsys.readouterr().out == ""  # 2a chamada nao gera novo log
```

- [ ] **Step 6: Rodar para confirmar as falhas**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_carrinho.py -v`
Expected: falhas em `AttributeError: module 'carrinho' has no attribute 'remover_item'` e afins.

- [ ] **Step 7: Implementar em `lambda/carrinho.py`**

Adicionar logo após `_resumo` (que também muda, veja abaixo) e antes de `adicionar_itens`:

```python
def _chave_item(it):
    """Assinatura de um item para decidir se e 'o mesmo' de outro (soma qtd em
    vez de duplicar linha)."""
    return (it["id"], it.get("tamanho"), it.get("borda"),
            tuple(it.get("meio_a_meio") or []), it.get("obs"))


def _mesclar_itens(existentes, novos):
    """Soma a quantidade de itens identicos (mesmo id/tamanho/borda/
    meio_a_meio/obs) em vez de duplicar a linha."""
    for novo in novos:
        chave_novo = _chave_item(novo)
        igual = next((it for it in existentes if _chave_item(it) == chave_novo), None)
        if igual:
            igual["qtd"] += novo["qtd"]
        else:
            existentes.append(novo)
```

Substituir `_resumo` (numera as linhas):

```python
def _resumo(cart):
    """Carrinho precificado para exibir (linhas com preco + subtotal + numero
    da posicao, usado por remover_item/alterar_quantidade)."""
    linhas, subtotal, erro = pedido.precificar(cart["loja"], cart["itens"])
    if erro:
        return {"erro": erro}
    for numero, linha in enumerate(linhas, start=1):
        linha["numero"] = numero
    return {
        "loja": LOJAS[cart["loja"]]["nome"],
        "itens": linhas,
        "quantidade_itens": sum(l["qtd"] for l in linhas),
        "subtotal": subtotal,
    }
```

Em `adicionar_itens`, trocar `cart["itens"].extend(novos)` por `_mesclar_itens(cart["itens"], novos)` (única mudança nesta Task; a Task 2 reescreve o resto da função):

```python
    cart["loja"] = loja_id
    _mesclar_itens(cart["itens"], novos)
    _salvar(session_attrs, cart)
```

Adicionar `remover_item` e `alterar_quantidade` logo após `ver_carrinho`:

```python
def remover_item(params, session_attrs):
    """Remove um item do carrinho pela posicao mostrada em ver_carrinho
    (campo 'numero' de cada linha, comecando em 1)."""
    cart = _carregar(session_attrs)
    if not cart["itens"]:
        return {"sucesso": False, "erro": "Carrinho vazio"}

    numero = params.get("numero")
    try:
        indice = int(numero) - 1
    except (TypeError, ValueError):
        return {"sucesso": False, "erro": f"Numero de item invalido: '{numero}'"}
    if indice < 0 or indice >= len(cart["itens"]):
        return {"sucesso": False,
                "erro": f"Nao existe item numero {numero}. O carrinho tem {len(cart['itens'])} item(ns)."}

    removido = cart["itens"].pop(indice)
    nome_removido = get_item(removido["id"])["nome"]

    if not cart["itens"]:
        session_attrs.pop(CHAVE, None)
        return {"sucesso": True, "mensagem": f"{nome_removido} removido. Carrinho vazio."}

    _salvar(session_attrs, cart)
    resultado = _resumo(cart)
    if "erro" in resultado:
        return {"sucesso": False,
                "erro": f"{nome_removido} removido, mas o carrinho ficou invalido: {resultado['erro']}"}
    resultado["sucesso"] = True
    resultado["mensagem"] = f"{nome_removido} removido."
    return resultado


def alterar_quantidade(params, session_attrs):
    """Altera a quantidade (ou, para itens por kg, os gramas) de um item ja
    no carrinho, pela posicao mostrada em ver_carrinho."""
    cart = _carregar(session_attrs)
    if not cart["itens"]:
        return {"sucesso": False, "erro": "Carrinho vazio"}

    numero = params.get("numero")
    try:
        indice = int(numero) - 1
    except (TypeError, ValueError):
        return {"sucesso": False, "erro": f"Numero de item invalido: '{numero}'"}
    if indice < 0 or indice >= len(cart["itens"]):
        return {"sucesso": False,
                "erro": f"Nao existe item numero {numero}. O carrinho tem {len(cart['itens'])} item(ns)."}

    nova_qtd, erro = pedido.parse_quantidade(params.get("quantidade"))
    if erro:
        return {"sucesso": False, "erro": erro}

    cart["itens"][indice]["qtd"] = nova_qtd
    _salvar(session_attrs, cart)

    resultado = _resumo(cart)
    if "erro" in resultado:
        return {"sucesso": False,
                "erro": f"Quantidade nao pode ser alterada: {resultado['erro']}"}
    resultado["sucesso"] = True
    resultado["mensagem"] = "Quantidade atualizada."
    return resultado
```

Por fim, dar idempotência a `finalizar_pedido` (adiciona só o bloco do topo; o resto da função é o que a Task 0 já deixou):

```python
def finalizar_pedido(params, session_attrs):
    """Revalida o carrinho, registra o pedido no log e esvazia o carrinho.

    Se chamado de novo (retry comum do Nova) com o carrinho ja vazio, devolve
    o ultimo pedido finalizado nesta sessao em vez de erro, com a flag
    ja_finalizado, no lugar de "Carrinho vazio".
    """
    cart = _carregar(session_attrs)
    if not cart["itens"] and CHAVE_ULTIMO_PEDIDO in session_attrs:
        ultimo = json.loads(session_attrs[CHAVE_ULTIMO_PEDIDO])
        ultimo["ja_finalizado"] = True
        return ultimo

    resultado = revisar_pedido(params, session_attrs)
    if not resultado.get("sucesso"):
        return resultado

    pedido_id = f"PED-{uuid.uuid4().hex[:8].upper()}"
    resultado["pedido_id"] = pedido_id
    resultado["cliente"] = params.get("nome_cliente")
    obs = (params.get("observacoes") or "").strip()
    if obs:
        resultado["observacoes"] = obs

    print(json.dumps({
        "evento": "pedido_finalizado",
        "pedido_id": pedido_id,
        "loja": resultado["loja"],
        "itens": resultado["itens"],
        "endereco": resultado["endereco_entrega"],
        "total": resultado["total"],
        "cliente": resultado["cliente"],
        "timestamp": geo.agora().isoformat(),
    }, ensure_ascii=False))

    session_attrs[CHAVE_ULTIMO_PEDIDO] = json.dumps(resultado, ensure_ascii=False)
    session_attrs.pop(CHAVE, None)
    return resultado
```

- [ ] **Step 8: Rodar para confirmar que passam**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_carrinho.py tests/test_pedido.py -v`
Expected: todos passam.

- [ ] **Step 9: Dispatch em `lambda/handler.py`** — adicionar 2 ramos no `if/elif` de `lambda_handler`, logo após `ver_carrinho` e antes de `limpar_carrinho`:

```python
    elif function == "ver_carrinho":
        result = carrinho.ver_carrinho(session_attrs)
    elif function == "remover_item":
        result = carrinho.remover_item(params, session_attrs)
    elif function == "alterar_quantidade":
        result = carrinho.alterar_quantidade(params, session_attrs)
    elif function == "limpar_carrinho":
```

- [ ] **Step 10: Schema em `agent.tf`** — inserir 2 blocos `functions` novos entre o bloco de `ver_carrinho` e o de `limpar_carrinho`:

```hcl
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
```

- [ ] **Step 11: 1 linha em `instructions.txt`** — logo após "Para recomeçar do zero, use limpar_carrinho." (linha 21):

```
- Para remover um item ou trocar a quantidade, use remover_item ou alterar_quantidade com o número da linha mostrado em ver_carrinho (sempre confira o carrinho antes de usar; nunca invente o número).
```

- [ ] **Step 12: `terraform validate`**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 13: Rodar a suite inteira**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/ -v`
Expected: todos passam.

- [ ] **Step 14: Commit**

```bash
git add lambda/pedido.py lambda/carrinho.py lambda/handler.py agent.tf instructions.txt tests/
git commit -m "$(cat <<'EOF'
feat: carrinho editavel (remover_item, alterar_quantidade) e finalizar_pedido idempotente

Carrinho so crescia: sem remover item nem mudar quantidade, e item identico
duplicava linha em vez de somar. Adiciona remover_item/alterar_quantidade
referenciando a posicao numerada mostrada em ver_carrinho, mescla itens
identicos (mesmo id/tamanho/borda/meio_a_meio/obs) e torna finalizar_pedido
idempotente: retry com carrinho ja vazio devolve o ultimo pedido (flag
ja_finalizado) em vez de "Carrinho vazio".
EOF
)"
```

---

### Task 2: Correções de lógica (parsing, dinheiro, horário, CEP, guardas do carrinho)

O grosso dos 44 achados: quantidade não numérica virava 1 em silêncio, observação sumia ou era truncada, dinheiro em float subcobrava meio centavo, janela que cruza meia-noite nunca abria a loja, ViaCEP fora do ar era indistinguível de CEP errado, qualquer CEP do Brasil era aceito, loja forçada era ignorada, e `adicionar_itens` podia devolver sucesso e erro juntos.

**Files:**
- Modify: `lambda/pedido.py` (`parse_itens`, `_preco_pizza`, `_monta_linha`, `precificar` — Decimal + fix de campos/obs)
- Modify: `lambda/dados.py` (loja A "até 24h" de verdade; `cidade`/`uf` por loja)
- Modify: `lambda/geo.py` (janela overnight, `consultar_cep` distingue indisponível de inexistente, `area_atendida`)
- Modify: `lambda/carrinho.py` (loja forçada explícita, sugestão de loja aberta alternativa, guarda sucesso+erro, `revisar_pedido` valida área de entrega)
- Modify: `lambda/handler.py` (`consultar_cardapio` valida/aceita nome de loja, `disponivel_agora` escopado pela loja filtrada, `obs_disponibilidade` completo, `p.get("value", "")` + try/except no dispatch)
- Modify: `tests/conftest.py` (mocks de CEP passam a usar a nova assinatura de `geo._get_json`)
- Test: `tests/test_pedido.py`, `tests/test_carrinho.py` (estendem), `tests/test_geo.py` (novo), `tests/test_handler.py` (novo)

**Interfaces:**
- Consumes (de Task 1): `pedido.parse_quantidade(texto) -> (valor, erro)`.
- Produces: `pedido.parse_itens(texto) -> (itens: list|None, erro: str|None)` — **muda de assinatura** (antes devolvia só a lista); todo chamador precisa desempacotar a tupla.
- Produces: `geo.area_atendida(loja: dict, endereco: dict) -> bool`.
- Produces: `geo._get_json(url, timeout=5) -> (dict|None, falha: str|None)` — **muda de assinatura** (antes devolvia só o dict ou `None`); `falha` é `None` em sucesso ou uma string descrevendo o problema.

- [ ] **Step 1: Atualizar `tests/conftest.py` para a nova assinatura de `_get_json` e adicionar os mocks de CEP inexistente/indisponível**

```python
"""Config comum dos testes: poe lambda/ no sys.path (os modulos de la usam
import direto, sem pacote) e mocks de rede para geo.consultar_cep."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import geo  # noqa: E402


def mock_cep_valido(monkeypatch, cidade="Sao Paulo", uf="SP", cep="01310100"):
    """Faz geo.consultar_cep responder com um endereco valido, sem rede."""
    resposta = {"logradouro": "Rua Teste", "bairro": "Centro", "localidade": cidade,
                "uf": uf, "cep": cep}
    monkeypatch.setattr(geo, "_get_json", lambda url, timeout=5: (resposta, None))


def mock_cep_inexistente(monkeypatch):
    """Faz geo.consultar_cep responder que o CEP nao existe (ViaCEP no ar,
    mas devolve {"erro": true})."""
    monkeypatch.setattr(geo, "_get_json", lambda url, timeout=5: ({"erro": True}, None))


def mock_cep_indisponivel(monkeypatch):
    """Faz toda chamada a geo._get_json falhar (simula ViaCEP fora do ar).
    Devolve um contador de chamadas para o teste checar o retry."""
    chamadas = {"n": 0}

    def falha(url, timeout=5):
        chamadas["n"] += 1
        return None, "indisponivel"

    monkeypatch.setattr(geo, "_get_json", falha)
    return chamadas
```

- [ ] **Step 2: Escrever os testes de `pedido.py` que ainda faltam (Decimal + parsing) — vão falhar**

Adicionar em `tests/test_pedido.py`:

```python
def test_parse_itens_qtd_omitida_usa_1():
    itens, erro = pedido.parse_itens("bb01")
    assert erro is None
    assert itens[0]["qtd"] == 1


def test_parse_itens_qtd_invalida_retorna_erro_sem_default_1():
    itens, erro = pedido.parse_itens("bb01|duas")
    assert itens is None
    assert erro is not None


def test_parse_itens_obs_com_pipe_nao_trunca():
    # obs digitada com '|' no meio: nada pode sumir depois do campo 5.
    itens, erro = pedido.parse_itens("pz04|1|grande|catupiry|pz01|capriche no queijo|sem cebola")
    assert erro is None
    assert itens[0]["obs"] == "capriche no queijo|sem cebola"


def test_parse_itens_campos_de_pizza_em_item_normal_vira_obs_em_vez_de_sumir():
    # hb01 nao e pizza: "sem picles" nao pode ser descartado no slot tamanho.
    itens, erro = pedido.parse_itens("hb01|2|sem picles")
    assert erro is None
    assert itens[0]["qtd"] == 2
    assert "tamanho" not in itens[0]
    assert "sem picles" in itens[0]["obs"]


def test_parse_itens_formato_documentado_com_obs_no_ultimo_campo():
    itens, erro = pedido.parse_itens("hb01|1||||sem cebola")
    assert erro is None
    assert itens[0]["obs"] == "sem cebola"


def test_precificar_peso_arredonda_half_up():
    # 250g x R$59,90/kg = 14,975 -> deve fechar em 14,98, nao 14,97 (bug de float).
    itens = [{"id": "sg01", "qtd": 250}]
    linhas, subtotal, erro = pedido.precificar("A", itens)
    assert erro is None
    assert linhas[0]["subtotal"] == 14.98
    assert subtotal == 14.98


def test_precificar_peso_abaixo_do_minimo_da_erro():
    itens = [{"id": "sg01", "qtd": 100}]
    _, _, erro = pedido.precificar("A", itens)
    assert erro is not None


def test_precificar_meio_a_meio_cobra_o_sabor_mais_caro():
    # pz01 Marguerita (grande 58.9) + pz03 Portuguesa (grande 63.9): cobra 63.9.
    itens = [{"id": "pz01", "qtd": 1, "tamanho": "grande", "meio_a_meio": ["pz01", "pz03"]}]
    linhas, subtotal, erro = pedido.precificar("A", itens)
    assert erro is None
    assert linhas[0]["subtotal"] == 63.9


def test_precificar_meio_a_meio_sabor_de_outra_loja_e_rejeitado():
    # pz01 so existe na loja A; tentar meio-a-meio com um sabor so-B deve falhar.
    itens = [{"id": "pz02", "qtd": 1, "tamanho": "media", "meio_a_meio": ["pz02", "pz01"]}]
    _, _, erro = pedido.precificar("B", itens)
    assert erro is not None


def test_precificar_tamanho_de_pizza_inexistente_da_erro():
    itens = [{"id": "pz01", "qtd": 1, "tamanho": "gigante"}]
    _, _, erro = pedido.precificar("A", itens)
    assert erro is not None


def test_precificar_borda_invalida_da_erro():
    itens = [{"id": "pz01", "qtd": 1, "tamanho": "media", "borda": "catupiry-duplo"}]
    _, _, erro = pedido.precificar("A", itens)
    assert erro is not None


def test_precificar_borda_soma_o_adicional():
    itens = [{"id": "pz01", "qtd": 1, "tamanho": "media", "borda": "catupiry"}]
    linhas, _, erro = pedido.precificar("A", itens)
    assert erro is None
    assert linhas[0]["subtotal"] == 45.9 + 8.0
```

- [ ] **Step 3: Rodar para confirmar as falhas**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_pedido.py -v`
Expected: várias falhas (`parse_itens` ainda devolve só a lista, sem tupla; `14.97 != 14.98`; etc).

- [ ] **Step 4: Reescrever `lambda/pedido.py` inteiro**

```python
"""Parsing e precificacao de itens — o motor de precos do carrinho.

Precos: pizza = tamanho escolhido (meio-a-meio = sabor mais caro) + borda;
combo = preco fixo; demais = preco do item. Dinheiro em Decimal com
arredondamento ROUND_HALF_UP em todo o calculo, convertido para float so na
saida (json nao serializa Decimal). Nao registra nada — quem monta e fecha o
pedido e o modulo carrinho.
"""

from decimal import Decimal, ROUND_HALF_UP

import geo
from dados import BORDAS, get_item

DUAS_CASAS = Decimal("0.01")


def _dinheiro(valor):
    """Converte numero (int/float/str) para Decimal com 2 casas, half-up."""
    return Decimal(str(valor)).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)


def parse_quantidade(texto):
    """Converte o texto de uma quantidade num inteiro positivo.

    Aceita numero puro (unidades ou, para itens por peso, gramas: "3", "500")
    ou peso com sufixo ("500g", "1kg" -> 1000g; aceita virgula decimal:
    "1,5kg" -> 1500g). Retorna (valor, erro): erro e None se valido, e nesse
    caso valor e sempre um inteiro > 0; caso contrario valor e None.
    """
    bruto = str(texto if texto is not None else "").strip().lower().replace(",", ".")
    if not bruto:
        return None, "Quantidade nao informada"

    if bruto.endswith("kg"):
        numero, fator = bruto[:-2].strip(), 1000
    elif bruto.endswith("g"):
        numero, fator = bruto[:-1].strip(), 1
    else:
        numero, fator = bruto, 1

    try:
        valor = round(float(numero) * fator)
    except ValueError:
        return None, f"Quantidade invalida: '{texto}'. Informe um numero, ex.: '2' ou, para itens por peso, '500g'"

    if valor <= 0:
        return None, f"Quantidade deve ser maior que zero: '{texto}'"
    return valor, None


def parse_itens(texto):
    """Converte o texto do pedido em lista de itens.

    Itens separados por ';', campos por '|' na ordem:
    id|qtd|tamanho|borda|meio_a_meio|obs. Apenas o id e obrigatorio;
    tamanho/borda/meio_a_meio valem so para pizza (meio_a_meio = id do 2o
    sabor) — para os demais itens, texto nesses campos e preservado como
    observacao em vez de descartado. Obs junta tudo a partir do 5o campo
    (join com '|') para nao truncar observacoes que contenham '|'.
    Ex.: "bb05|3 ; hb01|2 ; pz04|1|grande|catupiry|pz01|caprichar no queijo"

    Retorna (itens, erro). Em caso de erro (ex.: quantidade invalida), itens
    e None.
    """
    itens = []
    for bloco in texto.split(";"):
        bloco = bloco.strip()
        if not bloco:
            continue
        campos = [c.strip() for c in bloco.split("|")]
        item_id = campos[0]
        if not item_id:
            continue

        campo_qtd = campos[1] if len(campos) > 1 and campos[1] else "1"
        qtd, erro = parse_quantidade(campo_qtd)
        if erro:
            return None, f"Item {item_id}: {erro}"

        item = {"id": item_id, "qtd": qtd}
        produto = get_item(item_id)

        tamanho = campos[2] if len(campos) > 2 else ""
        borda = campos[3] if len(campos) > 3 else ""
        segundo_sabor = campos[4] if len(campos) > 4 else ""
        obs = "|".join(campos[5:]) if len(campos) > 5 else ""

        if produto and produto.get("tipo") == "pizza":
            if tamanho:
                item["tamanho"] = tamanho
            if borda:
                item["borda"] = borda
            if segundo_sabor:
                item["meio_a_meio"] = [item_id, segundo_sabor]
        else:
            # Tamanho/borda/meio_a_meio nao se aplicam a este item: preserva
            # como observacao em vez de descartar (ex.: "hb01|2|sem picles"
            # nao pode sumir so porque o campo esta na posicao errada).
            perdidos = [c for c in (tamanho, borda, segundo_sabor) if c]
            if perdidos:
                obs = " | ".join(perdidos + ([obs] if obs else []))

        if obs:
            item["obs"] = obs
        itens.append(item)
    return itens, None


def _preco_pizza(produto, tamanho, meio_a_meio, loja_id):
    """Retorna (preco_base: Decimal, [sabores]) ou (None, mensagem_erro)."""
    if tamanho not in produto["tamanhos"]:
        opcoes = ", ".join(produto["tamanhos"])
        return None, f"Tamanho invalido para {produto['nome']}. Opcoes: {opcoes}"

    precos = [_dinheiro(produto["tamanhos"][tamanho])]
    sabores = [produto["nome"]]

    for outro_id in meio_a_meio or []:
        if outro_id == produto["id"]:
            continue
        outro = get_item(outro_id)
        if not outro or outro.get("tipo") != "pizza":
            return None, f"Sabor de pizza invalido: {outro_id}"
        if loja_id not in outro["lojas"]:
            return None, f"O sabor {outro['nome']} nao esta disponivel nesta loja"
        if tamanho not in outro["tamanhos"]:
            return None, f"O sabor {outro['nome']} nao tem o tamanho {tamanho}"
        precos.append(_dinheiro(outro["tamanhos"][tamanho]))
        sabores.append(outro["nome"])

    # Meio-a-meio cobra pelo sabor mais caro.
    return max(precos), sabores


def _monta_linha(produto, pedido_item, loja_id):
    """Retorna (linha, erro). linha = dict com item/qtd/precos; erro = str|None."""
    qtd = int(pedido_item.get("qtd", 1))
    if qtd < 1:
        return None, f"Quantidade invalida para {produto['nome']}"
    obs = (pedido_item.get("obs") or "").strip()

    # Salgados sao vendidos por peso: aqui a "quantidade" (qtd) e em gramas.
    if produto["tipo"] == "peso":
        gramas = qtd
        minimo = produto.get("minimo_g", 0)
        if gramas < minimo:
            return None, f"{produto['nome']} tem pedido minimo de {minimo}g (voce pediu {gramas}g)"
        preco = (_dinheiro(produto["preco_por_kg"]) * gramas / Decimal(1000)).quantize(
            DUAS_CASAS, rounding=ROUND_HALF_UP)
        linha = {
            "item": f"{produto['nome']} ({gramas}g)",
            "qtd": 1,
            "gramas": gramas,
            "preco_kg": float(_dinheiro(produto["preco_por_kg"])),
            "subtotal": float(preco),
        }
        if obs:
            linha["obs"] = obs
        return linha, None

    if produto["tipo"] == "pizza":
        tamanho = (pedido_item.get("tamanho") or "").strip().lower()
        preco, sabores = _preco_pizza(produto, tamanho, pedido_item.get("meio_a_meio"), loja_id)
        if preco is None:
            return None, sabores  # sabores carrega a mensagem de erro
        borda = (pedido_item.get("borda") or "sem").strip().lower()
        if borda not in BORDAS:
            return None, f"Borda invalida. Opcoes: {', '.join(BORDAS)}"
        preco += _dinheiro(BORDAS[borda])
        nome = f"Pizza {'/'.join(sabores)} ({tamanho}"
        nome += f", borda {borda})" if borda != "sem" else ")"
    elif produto["tipo"] == "combo":
        preco = _dinheiro(produto["preco"])
        nome = f"{produto['nome']} (combo)"
    else:
        preco = _dinheiro(produto["preco"])
        nome = produto["nome"]

    subtotal = (preco * qtd).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)
    linha = {
        "item": nome,
        "qtd": qtd,
        "preco_unitario": float(preco),
        "subtotal": float(subtotal),
    }
    if obs:
        linha["obs"] = obs
    return linha, None


def precificar(loja_id, itens):
    """Valida e precifica os itens na loja. Retorna (linhas, subtotal, erro).

    Valida existencia do item, se e vendido na loja e se esta na janela de
    horario.
    """
    linhas = []
    subtotal = Decimal("0.00")
    for pedido_item in itens:
        produto = get_item(pedido_item.get("id"))
        if not produto:
            return None, 0.0, f"Item inexistente: {pedido_item.get('id')}"
        if loja_id not in produto["lojas"]:
            return None, 0.0, f"{produto['nome']} nao esta disponivel nesta loja"
        if not geo.item_disponivel(produto):
            return None, 0.0, (f"{produto['nome']} so esta disponivel das "
                               f"{produto['disponivel_de']} as {produto['disponivel_ate']}")
        linha, erro = _monta_linha(produto, pedido_item, loja_id)
        if erro:
            return None, 0.0, erro
        linhas.append(linha)
        subtotal += _dinheiro(linha["subtotal"])
    return linhas, float(subtotal), None
```

- [ ] **Step 5: Rodar para confirmar que os testes de `pedido.py` passam**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_pedido.py -v`
Expected: todos passam (inclusive os antigos — `parse_itens`/`_monta_linha` mantêm o comportamento correto que já funcionava).

- [ ] **Step 6: Ajustar `lambda/dados.py`** — loja A "até 24h" de verdade (fecha à meia-noite, não às 23:59) e `cidade`/`uf` por loja para a validação de área de entrega.

Old (bloco `"A"`, dentro de `horarios`):
```python
        "horarios": {
            0: [],
            1: [("18:00", "23:59")],
            2: [("18:00", "23:59")],
            3: [("18:00", "23:59")],
            4: [("18:00", "23:59")],
            5: [("18:00", "23:59")],
            6: [("18:00", "23:59")],
        },
        "frete_base": 6.0,
        "frete_gratis_acima": 90.0,
    },
```

New:
```python
        "horarios": {
            0: [],
            1: [("18:00", "00:00")],
            2: [("18:00", "00:00")],
            3: [("18:00", "00:00")],
            4: [("18:00", "00:00")],
            5: [("18:00", "00:00")],
            6: [("18:00", "00:00")],
        },
        "cidade": "Sao Paulo",
        "uf": "SP",
        "frete_base": 6.0,
        "frete_gratis_acima": 90.0,
    },
```

E no bloco `"B"`, adicionar as mesmas duas chaves (a loja B fica em São Paulo/SP também):

Old:
```python
        "frete_base": 8.0,
        "frete_gratis_acima": 70.0,
    },
}
```

New:
```python
        "cidade": "Sao Paulo",
        "uf": "SP",
        "frete_base": 8.0,
        "frete_gratis_acima": 70.0,
    },
}
```

- [ ] **Step 7: Escrever `tests/test_geo.py` — vai falhar (janela overnight ainda quebra; `area_atendida` não existe)**

```python
"""Testes de horario/disponibilidade/CEP/area de entrega."""

from datetime import datetime

import geo

from conftest import mock_cep_valido, mock_cep_inexistente, mock_cep_indisponivel
from dados import LOJAS

TZ = geo.TZ

LOJA_MADRUGADA = {
    "id": "X", "nome": "Loja Teste", "horarios": {1: [("22:00", "02:00")]},
}


def test_loja_aberta_dentro_da_janela_normal():
    momento = datetime(2026, 7, 14, 20, 0, tzinfo=TZ)  # terca 20h
    assert geo.loja_aberta(LOJAS["B"], momento) is True


def test_loja_aberta_fora_da_janela_normal():
    momento = datetime(2026, 7, 14, 16, 0, tzinfo=TZ)  # terca 16h, B fechada (entre almoco e jantar)
    assert geo.loja_aberta(LOJAS["B"], momento) is False


def test_loja_aberta_janela_overnight_antes_da_meia_noite():
    momento = datetime(2026, 7, 14, 23, 0, tzinfo=TZ)  # terca 23h
    assert geo.loja_aberta(LOJA_MADRUGADA, momento) is True


def test_loja_aberta_janela_overnight_depois_da_meia_noite():
    momento = datetime(2026, 7, 15, 1, 0, tzinfo=TZ)  # quarta 1h (madrugada de terca p/ quarta)
    assert geo.loja_aberta(LOJA_MADRUGADA, momento) is True


def test_loja_aberta_janela_overnight_ja_fechou():
    momento = datetime(2026, 7, 15, 3, 0, tzinfo=TZ)  # quarta 3h, ja passou das 2h
    assert geo.loja_aberta(LOJA_MADRUGADA, momento) is False


def test_loja_a_fronteira_23_59_ainda_aberta():
    momento = datetime(2026, 7, 14, 23, 59, tzinfo=TZ)  # terca 23:59
    assert geo.loja_aberta(LOJAS["A"], momento) is True


def test_loja_a_fronteira_00_00_ainda_aberta_ate_24h():
    momento = datetime(2026, 7, 15, 0, 0, tzinfo=TZ)  # quarta 00:00 (fim da janela de terca)
    assert geo.loja_aberta(LOJAS["A"], momento) is True


def test_loja_a_00_01_ja_fechada():
    momento = datetime(2026, 7, 15, 0, 1, tzinfo=TZ)
    assert geo.loja_aberta(LOJAS["A"], momento) is False


def test_item_disponivel_dentro_e_fora_da_janela():
    item = {"disponivel_de": "07:00", "disponivel_ate": "11:00"}
    assert geo.item_disponivel(item, datetime(2026, 7, 14, 9, 0, tzinfo=TZ)) is True
    assert geo.item_disponivel(item, datetime(2026, 7, 14, 12, 0, tzinfo=TZ)) is False


def test_item_disponivel_sem_janela_sempre_disponivel():
    assert geo.item_disponivel({}, datetime(2026, 7, 14, 3, 0, tzinfo=TZ)) is True


def test_item_disponivel_overnight():
    item = {"disponivel_de": "22:00", "disponivel_ate": "02:00"}
    assert geo.item_disponivel(item, datetime(2026, 7, 14, 1, 0, tzinfo=TZ)) is True
    assert geo.item_disponivel(item, datetime(2026, 7, 14, 3, 0, tzinfo=TZ)) is False


def test_consultar_cep_valido(monkeypatch):
    mock_cep_valido(monkeypatch, cidade="Sao Paulo", uf="SP")
    resultado = geo.consultar_cep("01310-100")
    assert resultado["valido"] is True
    assert resultado["endereco"]["uf"] == "SP"


def test_consultar_cep_formato_invalido():
    resultado = geo.consultar_cep("123")
    assert resultado["valido"] is False


def test_consultar_cep_inexistente(monkeypatch):
    mock_cep_inexistente(monkeypatch)
    resultado = geo.consultar_cep("00000000")
    assert resultado["valido"] is False
    assert "nao encontrado" in resultado["erro"].lower()


def test_consultar_cep_servico_indisponivel_tenta_de_novo_antes_de_desistir(monkeypatch):
    chamadas = mock_cep_indisponivel(monkeypatch)
    resultado = geo.consultar_cep("01310100")
    assert resultado["valido"] is False
    assert "indispon" in resultado["erro"].lower()
    assert chamadas["n"] == 2  # 1 tentativa + 1 retry


def test_area_atendida_mesma_cidade():
    endereco = {"cidade": "Sao Paulo", "uf": "SP"}
    assert geo.area_atendida(LOJAS["A"], endereco) is True


def test_area_atendida_ignora_acento_e_caixa():
    endereco = {"cidade": "São Paulo", "uf": "sp"}
    assert geo.area_atendida(LOJAS["A"], endereco) is True


def test_area_atendida_fora_da_area():
    endereco = {"cidade": "Manaus", "uf": "AM"}
    assert geo.area_atendida(LOJAS["A"], endereco) is False
```

- [ ] **Step 8: Rodar para confirmar as falhas**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_geo.py -v`
Expected: falhas nos testes de overnight/fronteira e `AttributeError: module 'geo' has no attribute 'area_atendida'`.

- [ ] **Step 9: Reescrever `lambda/geo.py` inteiro**

```python
"""Horarios de funcionamento, disponibilidade de itens, consulta de CEP,
area de entrega e frete.

Sem coordenadas ou distancia: o CEP e validado (endereco via ViaCEP) contra a
cidade/UF da loja, e o frete e fixo por loja.
"""

import json
import unicodedata
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


# ---------------------------------------------------------------- tempo / horario

def agora():
    """Datetime atual no fuso de Sao Paulo."""
    return datetime.now(TZ)


def _minutos(hhmm):
    """'18:30' -> 1110 (minutos desde a meia-noite)."""
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def _cruza_meia_noite(abre, fecha):
    return _minutos(fecha) < _minutos(abre)


def _dentro_da_faixa(atual, abre, fecha):
    """True se 'atual' (minutos desde 0h) esta dentro de abre-fecha. Se fecha
    < abre, a faixa cruza a meia-noite (ex.: 18:00-02:00 ou 18:00-00:00 para
    "ate 24h") e conta como aberta da abertura ate a meia-noite OU da meia-
    noite ate o fechamento."""
    abre_min, fecha_min = _minutos(abre), _minutos(fecha)
    if fecha_min < abre_min:
        return atual >= abre_min or atual <= fecha_min
    return abre_min <= atual <= fecha_min


def loja_aberta(loja, momento=None):
    """True se a loja esta dentro de alguma faixa de funcionamento agora.

    Considera tambem as faixas do dia anterior que cruzam a meia-noite (ex.:
    terca 18:00-00:00 continua "aberta" no instante 00:00 de quarta)."""
    momento = momento or agora()
    atual = momento.hour * 60 + momento.minute

    faixas_hoje = loja["horarios"].get(momento.weekday(), [])
    if any(_dentro_da_faixa(atual, abre, fecha) for abre, fecha in faixas_hoje):
        return True

    dia_anterior = (momento.weekday() - 1) % 7
    faixas_ontem = loja["horarios"].get(dia_anterior, [])
    return any(_cruza_meia_noite(abre, fecha) and atual <= _minutos(fecha)
               for abre, fecha in faixas_ontem)


def item_disponivel(item, momento=None):
    """True se o item nao tem janela de horario ou se estamos dentro dela
    (mesma logica de janela cruzando meia-noite de loja_aberta)."""
    de, ate = item.get("disponivel_de"), item.get("disponivel_ate")
    if not de or not ate:
        return True
    momento = momento or agora()
    atual = momento.hour * 60 + momento.minute
    return _dentro_da_faixa(atual, de, ate)


# ---------------------------------------------------------------- CEP / area de entrega

def _normalizar(texto):
    """minusculo, sem acento, sem espaco nas bordas — para comparar cidade/UF."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower()


def _get_json(url, timeout=5):
    """GET simples. Retorna (dict, None) em sucesso, ou (None, motivo) se a
    chamada falhar (timeout, erro de rede, resposta que nao e JSON) — para
    distinguir "servico fora do ar" de "servico respondeu que nao existe"."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agente-pedidos-estudo"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), None
    except Exception:
        return None, "indisponivel"


def consultar_cep(cep):
    """Valida o CEP e retorna o endereco (via ViaCEP).

    {"valido": True, "endereco": {...}} ou {"valido": False, "erro": "..."}.
    Distingue CEP inexistente (ViaCEP respondeu "nao existe") de servico fora
    do ar (timeout/erro de rede: tenta mais uma vez antes de desistir).
    """
    digitos = "".join(c for c in str(cep) if c.isdigit())
    if len(digitos) != 8:
        return {"valido": False, "erro": "CEP deve conter 8 digitos"}

    url = f"https://viacep.com.br/ws/{digitos}/json/"
    via, falha = _get_json(url)
    if falha:
        via, falha = _get_json(url)  # 1 retry curto antes de desistir
    if falha:
        return {"valido": False,
                "erro": "Servico de CEP indisponivel no momento, tente de novo em instantes"}

    if via and not via.get("erro"):
        return {
            "valido": True,
            "endereco": {
                "logradouro": via.get("logradouro"),
                "bairro": via.get("bairro"),
                "cidade": via.get("localidade"),
                "uf": via.get("uf"),
                "cep": digitos,
            },
        }

    return {"valido": False, "erro": "CEP nao encontrado"}


def area_atendida(loja, endereco):
    """True se a cidade/UF do endereco batem com a area de entrega da loja
    (comparacao por cidade, sem acento/caixa)."""
    return (_normalizar(endereco.get("cidade")) == _normalizar(loja["cidade"])
            and (endereco.get("uf") or "").strip().upper() == loja["uf"])


# ---------------------------------------------------------------- frete

def frete_da_loja(loja, subtotal=0.0):
    """Frete fixo da loja, gratis a partir do valor configurado."""
    gratis = subtotal >= loja["frete_gratis_acima"]
    return {"frete": 0.0 if gratis else loja["frete_base"], "gratis": gratis}
```

- [ ] **Step 10: Rodar para confirmar que os testes de `geo.py` passam**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_geo.py -v`
Expected: todos passam.

- [ ] **Step 11: Estender `tests/test_carrinho.py` (loja forçada, sugestão de alternativa, guarda sucesso+erro) — vão falhar**

```python
def test_loja_forcada_diferente_da_do_carrinho_da_erro_explicito(monkeypatch):
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}
    carrinho.adicionar_itens({"itens": "hb01|1", "loja": "A"}, session_attrs)

    resultado = carrinho.adicionar_itens({"itens": "hb02|1", "loja": "B"}, session_attrs)

    assert resultado["sucesso"] is False
    assert "loja" in resultado["erro"].lower()


def test_loja_fechada_sugere_loja_aberta_alternativa(monkeypatch):
    # pz02 (Calabresa) existe em A e B; se so B estiver "aberta" no momento
    # simulado e a pessoa pedir explicitamente a A (fechada), deve sugerir B.
    momento_so_b_aberta = datetime(2026, 7, 14, 10, 0, tzinfo=geo.TZ)  # terca 10h: A fechada, B aberta
    monkeypatch.setattr(geo, "agora", lambda: momento_so_b_aberta)
    session_attrs = {}

    resultado = carrinho.adicionar_itens({"itens": "pz02|1|media", "loja": "A"}, session_attrs)

    assert resultado["sucesso"] is False
    assert resultado["loja_fechada"] is True
    assert "burger jardins" in resultado["erro"].lower()


def test_adicionar_itens_nunca_devolve_sucesso_true_com_erro(monkeypatch):
    # cf01 (cafe da manha) so esta disponivel 07:00-11:00. Adiciona dentro da
    # janela, depois o tempo "passa" e um segundo add deve reportar que o
    # carrinho ficou invalido, sem alegar sucesso.
    session_attrs = {}
    monkeypatch.setattr(geo, "agora", lambda: datetime(2026, 7, 14, 8, 0, tzinfo=geo.TZ))
    r1 = carrinho.adicionar_itens({"itens": "cf01|1"}, session_attrs)
    assert r1["sucesso"] is True

    monkeypatch.setattr(geo, "agora", lambda: datetime(2026, 7, 14, 12, 0, tzinfo=geo.TZ))
    r2 = carrinho.adicionar_itens({"itens": "bb01|1"}, session_attrs)

    assert r2["sucesso"] is False
    assert not (r2.get("sucesso") is True and "erro" in r2)  # nunca sucesso=True junto com erro
    assert r2.get("sucesso") is False


def test_revisar_pedido_fora_da_area_de_entrega_da_erro(monkeypatch):
    from conftest import mock_cep_valido
    mock_cep_valido(monkeypatch, cidade="Manaus", uf="AM")
    session_attrs = _carrinho_com_pizza(monkeypatch)

    resultado = carrinho.revisar_pedido({"cep": "69020030"}, session_attrs)

    assert resultado["sucesso"] is False
    assert "area de entrega" in resultado["erro"].lower()
```

- [ ] **Step 12: Rodar para confirmar as falhas**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_carrinho.py -v`
Expected: falhas nos 4 testes novos (loja forçada ainda ignorada em silêncio; mensagem de loja fechada ainda genérica; sucesso+erro ainda coexistem; `revisar_pedido` ainda não valida área).

- [ ] **Step 13: Reescrever as partes afetadas de `lambda/carrinho.py`**

Substituir `_escolher_loja` (adiciona `_lojas_candidatas` como helper extraído):

```python
def _lojas_candidatas(novos):
    """Lojas que vendem TODOS os itens do pedido (independente de estar aberta)."""
    return [lid for lid in LOJAS if all(lid in _lojas_efetivas(i) for i in novos)]


def _escolher_loja(novos, forcada):
    """Escolhe a loja para itens num carrinho vazio. Retorna (loja_id, erro).

    Prefere uma loja aberta que venda TODOS os itens. Se a pessoa indicou uma
    loja (forcada), respeita — desde que ela tenha os itens.
    """
    candidatas = _lojas_candidatas(novos)
    if not candidatas:
        return None, ("Esses itens nao estao todos na mesma loja. Um pedido e de uma loja so — "
                      "posso comecar por uma e depois fazer outro pedido.")
    if forcada:
        if forcada not in candidatas:
            return None, f"Esses itens nao estao disponiveis na loja {LOJAS[forcada]['nome']}."
        return forcada, None
    abertas = [lid for lid in candidatas if geo.loja_aberta(LOJAS[lid])]
    return (abertas or candidatas)[0], None
```

Substituir `adicionar_itens` inteira:

```python
def adicionar_itens(params, session_attrs):
    novos, erro = pedido.parse_itens(params.get("itens", ""))
    if erro:
        return {"sucesso": False, "erro": erro}
    if not novos:
        return {"sucesso": False, "erro": "Nenhum item informado"}
    for it in novos:
        for sabor in _ids_do_item(it):  # inclui os sabores do meio-a-meio
            if not get_item(sabor):
                return {"sucesso": False, "erro": f"Item inexistente: {sabor}"}

    forcada = (params.get("loja") or "").strip().upper() or None
    if forcada and forcada not in LOJAS:
        return {"sucesso": False, "erro": "Loja invalida. Escolha A ou B."}

    cart = _carregar(session_attrs)
    if cart["itens"]:
        # Carrinho ja tem loja: os novos itens (e uma loja forcada, se houver)
        # precisam ser dela — nunca ignorar em silencio.
        loja_id = cart["loja"]
        if forcada and forcada != loja_id:
            return {"sucesso": False,
                    "erro": (f"Seu carrinho ja esta com itens da {LOJAS[loja_id]['nome']}. Um pedido "
                             f"e de uma loja so: finalize ou limpe o carrinho antes de pedir da "
                             f"{LOJAS[forcada]['nome']}.")}
        fora = [get_item(i["id"])["nome"] for i in novos if loja_id not in _lojas_efetivas(i)]
        if fora:
            return {"sucesso": False,
                    "erro": (f"{', '.join(fora)} nao e da loja {LOJAS[loja_id]['nome']}, onde seu "
                             "carrinho esta. Um pedido e de uma loja so: posso finalizar ou limpar "
                             "o carrinho atual antes de trocar de loja.")}
    else:
        loja_id, erro = _escolher_loja(novos, forcada)
        if erro:
            return {"sucesso": False, "erro": erro}

    # Loja fechada: nao aceita pedido (nao monta carrinho que nao fecha).
    loja = LOJAS[loja_id]
    if not geo.loja_aberta(loja):
        candidatas = _lojas_candidatas(novos)
        abertas = [LOJAS[lid] for lid in candidatas if lid != loja_id and geo.loja_aberta(LOJAS[lid])]
        if abertas:
            nomes = ", ".join(l["nome"] for l in abertas)
            return {"sucesso": False, "loja_fechada": True, "loja": loja["nome"],
                    "horario": loja["horario_texto"],
                    "erro": (f"A {loja['nome']} esta fechada agora ({loja['horario_texto']}). Esses "
                             f"itens tambem tem na {nomes}, que esta aberta agora — quer pedir de la?")}
        return {"sucesso": False, "loja_fechada": True, "loja": loja["nome"],
                "horario": loja["horario_texto"],
                "erro": (f"A {loja['nome']} esta fechada agora ({loja['horario_texto']}). Esse item so "
                         "e vendido nela; nenhuma loja aberta agora tem esse item. So da pra pedir "
                         "quando ela reabrir.")}

    # Valida horario dos itens e precifica antes de guardar.
    _, _, erro = pedido.precificar(loja_id, novos)
    if erro:
        return {"sucesso": False, "erro": erro}

    cart["loja"] = loja_id
    _mesclar_itens(cart["itens"], novos)
    _salvar(session_attrs, cart)

    resultado = _resumo(cart)
    if "erro" in resultado:
        return {"sucesso": False,
                "erro": f"Item adicionado, mas o carrinho ficou invalido: {resultado['erro']}"}
    resultado["sucesso"] = True
    resultado["mensagem"] = "Itens adicionados. Deseja mais alguma coisa ou fechar o pedido?"
    return resultado
```

Substituir `revisar_pedido` (adiciona a checagem de área de entrega):

```python
def revisar_pedido(params, session_attrs):
    """Resumo final com frete e total para um CEP, sem registrar."""
    cart = _carregar(session_attrs)
    if not cart["itens"]:
        return {"sucesso": False, "erro": "Carrinho vazio"}

    loja = LOJAS[cart["loja"]]
    if not geo.loja_aberta(loja):
        return {"sucesso": False,
                "erro": f"A loja {loja['nome']} esta fechada agora. Horario: {loja['horario_texto']}"}

    endereco = geo.consultar_cep(params.get("cep", ""))
    if not endereco.get("valido"):
        return {"sucesso": False, "erro": endereco.get("erro", "CEP invalido")}
    if not geo.area_atendida(loja, endereco["endereco"]):
        return {"sucesso": False,
                "erro": (f"Esse CEP fica fora da area de entrega da {loja['nome']} "
                         f"(atende {loja['cidade']}/{loja['uf']}). Nao da pra entregar ai.")}

    linhas, subtotal, erro = pedido.precificar(cart["loja"], cart["itens"])
    if erro:
        return {"sucesso": False, "erro": erro}

    entrega = geo.frete_da_loja(loja, subtotal)
    return {
        "sucesso": True,
        "loja": loja["nome"],
        "endereco_entrega": endereco["endereco"],
        "itens": linhas,
        "subtotal": subtotal,
        "frete": entrega["frete"],
        "frete_gratis": entrega["gratis"],
        "total": round(subtotal + entrega["frete"], 2),
    }
```

- [ ] **Step 14: Rodar para confirmar que os testes de `carrinho.py` passam**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_carrinho.py -v`
Expected: todos passam.

- [ ] **Step 15: Escrever `tests/test_handler.py` — vai falhar**

```python
"""Testes do dispatch da Lambda: consultar_cardapio, envelope de resposta,
robustez contra parametro sem 'value' e excecao interna."""

import json

import handler


def _evento(function, parametros=None, session_attrs=None):
    return {
        "actionGroup": "pedidos",
        "function": function,
        "parameters": [{"name": k, "value": v} for k, v in (parametros or {}).items()],
        "sessionAttributes": session_attrs or {},
    }


def _corpo(resposta):
    texto = resposta["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    return json.loads(texto)


def test_lambda_handler_dispatch_ok():
    resposta = handler.lambda_handler(_evento("listar_lojas"), None)
    corpo = _corpo(resposta)
    assert len(corpo["lojas"]) == 2


def test_lambda_handler_funcao_desconhecida_nao_quebra():
    resposta = handler.lambda_handler(_evento("voar_para_a_lua"), None)
    corpo = _corpo(resposta)
    assert "erro" in corpo


def test_lambda_handler_parametro_sem_value_nao_derruba_a_lambda():
    evento = {
        "actionGroup": "pedidos",
        "function": "consultar_cardapio",
        "parameters": [{"name": "categoria"}],  # sem "value"
        "sessionAttributes": {},
    }
    resposta = handler.lambda_handler(evento, None)
    corpo = _corpo(resposta)
    assert "categorias" in corpo or "itens" in corpo or "erro" in corpo


def test_lambda_handler_excecao_interna_vira_erro_estruturado(monkeypatch):
    def explode(session_attrs):
        raise RuntimeError("boom")

    monkeypatch.setattr(handler.carrinho, "ver_carrinho", explode)
    resposta = handler.lambda_handler(_evento("ver_carrinho"), None)
    corpo = _corpo(resposta)
    assert "erro" in corpo
    assert resposta["messageVersion"] == "1.0"  # envelope continua valido


def test_consultar_cardapio_loja_invalida_da_erro_em_vez_de_lista_vazia():
    resposta = handler.lambda_handler(
        _evento("consultar_cardapio", {"categoria": "bebidas", "loja": "Z"}), None)
    corpo = _corpo(resposta)
    assert "erro" in corpo


def test_consultar_cardapio_aceita_nome_da_loja():
    resposta = handler.lambda_handler(
        _evento("consultar_cardapio", {"categoria": "pizzas", "loja": "pizzaria central"}), None)
    corpo = _corpo(resposta)
    assert corpo["quantidade"] > 0
    assert all("A" in it["lojas"] for it in corpo["itens"])


def test_consultar_cardapio_disponivel_agora_considera_so_a_loja_filtrada(monkeypatch):
    import geo
    from datetime import datetime
    # terca 10h: A fechada, B aberta. pz02 (Calabresa) existe nas duas.
    monkeypatch.setattr(geo, "agora", lambda: datetime(2026, 7, 14, 10, 0, tzinfo=geo.TZ))

    resposta = handler.lambda_handler(
        _evento("consultar_cardapio", {"categoria": "pizzas", "loja": "A"}), None)
    corpo = _corpo(resposta)
    item = next(it for it in corpo["itens"] if it["id"] == "pz02")
    assert item["disponivel_agora"] is False
    assert "pizzaria central" in item["obs_disponibilidade"].lower()
```

- [ ] **Step 16: Rodar para confirmar as falhas**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_handler.py -v`
Expected: falhas (`loja` não validada; `KeyError: 'value'`; exceção derruba o teste; `disponivel_agora` olhando a loja errada).

- [ ] **Step 17: Reescrever `lambda/handler.py` inteiro**

```python
"""Entrada da Lambda do action group. Faz o dispatch para as funcoes do agente.

Funcoes: consultar_cardapio, listar_lojas, adicionar_itens, ver_carrinho,
remover_item, alterar_quantidade, limpar_carrinho, revisar_pedido,
finalizar_pedido. As funcoes de carrinho leem e escrevem o carrinho em
sessionAttributes, que o Bedrock mantem entre os turnos.
"""

import json

import carrinho
import geo
from dados import CARDAPIO, CATEGORIAS, LOJAS


def _normalizar(texto):
    """minusculo, sem acento, sem espaco nas bordas — para comparar nomes de loja."""
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower()


def _resolver_loja(texto):
    """Aceita 'A'/'B' ou o nome da loja (case/acento insensivel). Retorna o
    id ou None se nao reconhecer."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if texto.upper() in LOJAS:
        return texto.upper()
    normalizado = _normalizar(texto)
    for loja in LOJAS.values():
        if _normalizar(loja["nome"]) == normalizado:
            return loja["id"]
    return None


def consultar_cardapio(params):
    """Sem categoria: lista as categorias. Com categoria: itens da categoria,
    opcionalmente filtrados pela loja (aceita id A/B ou o nome da loja)."""
    categoria = (params.get("categoria") or "").strip().lower()
    loja_bruta = (params.get("loja") or "").strip()
    loja_id = None
    if loja_bruta:
        loja_id = _resolver_loja(loja_bruta)
        if not loja_id:
            return {"erro": f"Loja invalida: '{loja_bruta}'. Use listar_lojas para ver as lojas existentes."}

    if not categoria:
        return {
            "categorias": [{"chave": k, "nome": v} for k, v in CATEGORIAS.items()],
            "instrucao": "Chame consultar_cardapio novamente com o parametro 'categoria'.",
        }
    if categoria not in CATEGORIAS:
        return {"erro": f"Categoria invalida: {categoria}", "categorias": list(CATEGORIAS)}

    itens = []
    for it in CARDAPIO:
        if it["categoria"] != categoria:
            continue
        if loja_id and loja_id not in it["lojas"]:
            continue
        # Com filtro de loja, disponibilidade considera SO a loja filtrada
        # (senao "disponivel_agora" fica contraditorio com adicionar_itens).
        lojas_relevantes = [loja_id] if loja_id else it["lojas"]
        na_janela = geo.item_disponivel(it)
        loja_aberta_agora = any(geo.loja_aberta(LOJAS[l]) for l in lojas_relevantes)
        registro = {
            "id": it["id"],
            "nome": it["nome"],
            "descricao": it["descricao"],
            "lojas": it["lojas"],
            "disponivel_agora": na_janela and loja_aberta_agora,
        }
        if not registro["disponivel_agora"]:
            lojas_txt = "; ".join(f"{LOJAS[l]['nome']} ({LOJAS[l]['horario_texto']})"
                                  for l in lojas_relevantes)
            if not na_janela:
                registro["obs_disponibilidade"] = (
                    f"disponivel so das {it['disponivel_de']} as {it['disponivel_ate']}; "
                    f"vendido na {lojas_txt}")
            else:
                registro["obs_disponibilidade"] = f"vendido so na {lojas_txt}, fechada agora"
        if it["tipo"] == "pizza":
            registro["tamanhos"] = it["tamanhos"]
            registro["meio_a_meio"] = True
        elif it["tipo"] == "combo":
            registro["preco"] = it["preco"]
            registro["inclui"] = it["inclui"]
        elif it["tipo"] == "peso":
            registro["preco_por_kg"] = it["preco_por_kg"]
            registro["minimo_g"] = it["minimo_g"]
            registro["unidade"] = "kg (pedido em gramas)"
        else:
            registro["preco"] = it["preco"]
        if it.get("disponivel_de"):
            registro["horario"] = f"{it['disponivel_de']}-{it['disponivel_ate']}"
        itens.append(registro)

    return {"categoria": categoria, "quantidade": len(itens), "itens": itens}


def listar_lojas():
    """As 2 lojas com endereco, horario, frete e se estao abertas agora."""
    return {"lojas": [{
        "id": loja["id"],
        "nome": loja["nome"],
        "endereco": loja["endereco"],
        "horario": loja["horario_texto"],
        "aberta_agora": geo.loja_aberta(loja),
        "frete_base": loja["frete_base"],
        "frete_gratis_acima": loja["frete_gratis_acima"],
    } for loja in LOJAS.values()]}


def lambda_handler(event, context):
    function = event.get("function", "")
    params = {p["name"]: p.get("value", "") for p in event.get("parameters", [])}
    session_attrs = dict(event.get("sessionAttributes") or {})

    try:
        if function == "consultar_cardapio":
            result = consultar_cardapio(params)
        elif function == "listar_lojas":
            result = listar_lojas()
        elif function == "adicionar_itens":
            result = carrinho.adicionar_itens(params, session_attrs)
        elif function == "ver_carrinho":
            result = carrinho.ver_carrinho(session_attrs)
        elif function == "remover_item":
            result = carrinho.remover_item(params, session_attrs)
        elif function == "alterar_quantidade":
            result = carrinho.alterar_quantidade(params, session_attrs)
        elif function == "limpar_carrinho":
            result = carrinho.limpar_carrinho(session_attrs)
        elif function == "revisar_pedido":
            result = carrinho.revisar_pedido(params, session_attrs)
        elif function == "finalizar_pedido":
            result = carrinho.finalizar_pedido(params, session_attrs)
        else:
            result = {"erro": f"Funcao desconhecida: {function}"}
    except Exception as exc:
        print(json.dumps({"evento": "erro_dispatch", "function": function, "erro": str(exc)},
                          ensure_ascii=False))
        result = {"erro": "Erro interno ao processar o pedido. Tente novamente."}

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup"),
            "function": function,
            "functionResponse": {
                "responseBody": {"TEXT": {"body": json.dumps(result, ensure_ascii=False)}}
            },
        },
        "sessionAttributes": session_attrs,
        "promptSessionAttributes": event.get("promptSessionAttributes", {}),
    }
```

- [ ] **Step 18: Rodar para confirmar que os testes de `handler.py` passam**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/test_handler.py -v`
Expected: todos passam.

- [ ] **Step 19: `terraform validate`**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 20: Rodar a suite inteira**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/ -v`
Expected: todos passam.

- [ ] **Step 21: Commit**

```bash
git add lambda/pedido.py lambda/dados.py lambda/geo.py lambda/carrinho.py lambda/handler.py tests/
git commit -m "$(cat <<'EOF'
fix: corrigir parsing, dinheiro, janela overnight, validacao de CEP e guardas do carrinho

Corrige a maior parte dos achados medios/altos da avaliacao 2026-07-11:
quantidade nao numerica virava 1 em silencio (agora erro explicito, aceita
"500g"/"1kg"); observacao em item nao-pizza sumia e obs com "|" era truncada
(agora preservadas); dinheiro em float subcobrava meio centavo no peso (agora
Decimal com ROUND_HALF_UP); janela cruzando meia-noite nunca abria a loja
(loja A alinhada ao "ate 24h" do texto); ViaCEP fora do ar era indistinguivel
de CEP invalido (agora retry + mensagem propria) e qualquer CEP do Brasil era
aceito (agora valida cidade/UF contra a loja); loja forcada diferente da do
carrinho era ignorada em silencio; "nenhuma loja aberta tem esse item" era
dito mesmo quando falso; adicionar_itens podia devolver sucesso=True com
erro; consultar_cardapio nao validava loja e calculava disponibilidade
olhando lojas erradas quando filtrado; handler nao tratava parametro sem
'value' nem excecoes internas.
EOF
)"
```

---

### Task 3: Schema, infra e documentação

Fecha os achados de infra/documentação que sobraram: categoria ausente do enum, TTL curto demais para qualquer canal com pausas, zip da Lambda carregando `__pycache__`, `invoke.py` com IDs que apodrecem a cada deploy, e o README desalinhado com a realidade (Nova Lite, contagem de funções).

**Files:**
- Modify: `agent.tf` (categoria "salgados", exemplo de `obs`, TTL)
- Modify: `lambda.tf` (excludes do zip)
- Modify: `invoke.py` (sem IDs default, região via env var)
- Modify: `README.md` (Nova Pro, lista de funções completa, seção "Persistência")

**Interfaces:** nenhuma nova — esta Task não muda comportamento de runtime, só schema/infra/docs.

- [ ] **Step 1: `agent.tf` — categoria "salgados" ausente do enum**

Old:
```hcl
          description   = "Categoria: pizzas, hamburgueres, combos, porcoes, massas, japonesa, saladas, cafe_da_manha, bebidas ou sobremesas"
```

New:
```hcl
          description   = "Categoria: pizzas, hamburgueres, combos, porcoes, salgados, massas, japonesa, saladas, cafe_da_manha, bebidas ou sobremesas"
```

> Nota: o ideal seria gerar essa lista a partir de `CATEGORIAS` (dados.py) via `locals`/`templatefile` para nunca divergir de novo. Não fiz isso agora porque exigiria uma fonte de dados externa (Terraform não lê dicionários Python) — ou uma `external` data source chamando `python3`, que conta como "recurso novo" e está fora do escopo desta fase. Registrar como item de infra para uma fase futura se o cardápio crescer mais.

- [ ] **Step 2: `agent.tf` — documentar `obs` com exemplo literal**

Old:
```hcl
          description   = "Itens separados por ';' e campos por '|' nesta ordem: id|qtd|tamanho|borda|meio_a_meio|obs. Apenas o id e obrigatorio. tamanho, borda e meio_a_meio sao so para pizza (meio_a_meio = id do 2o sabor). Para salgados (vendidos por kg) a quantidade e em GRAMAS, ex.: 'sg01|500' = 500g. Ex.: 'bb05|3 ; hb01|2 ; pz04|1|grande|catupiry|pz01 ; sg01|500'"
```

New:
```hcl
          description   = "Itens separados por ';' e campos por '|' nesta ordem: id|qtd|tamanho|borda|meio_a_meio|obs. Apenas o id e obrigatorio. tamanho, borda e meio_a_meio sao so para pizza (meio_a_meio = id do 2o sabor); para os demais itens deixe-os vazios ate chegar no campo obs. Para salgados (vendidos por kg) a quantidade e em GRAMAS ou com sufixo, ex.: 'sg01|500' ou 'sg01|1kg' = 1000g. Observacao (obs) e sempre o ultimo campo: para pizza, 'pz04|1|grande|catupiry|pz01|caprichar no queijo'; para os demais itens, 'hb01|1||||sem cebola' (hamburguer sem cebola). Ex. completo: 'bb05|3 ; hb01|2 ; pz04|1|grande|catupiry|pz01 ; sg01|500 ; hb02|1||||sem cebola'"
```

- [ ] **Step 3: `agent.tf` — TTL da sessão 600 → 3600**

Old:
```hcl
  idle_session_ttl_in_seconds = 600
```

New:
```hcl
  idle_session_ttl_in_seconds = 3600
```

- [ ] **Step 4: `lambda.tf` — excludes de `__pycache__`/`*.pyc` no zip**

Old:
```hcl
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda_payload.zip"
}
```

New:
```hcl
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda_payload.zip"
  excludes    = ["__pycache__", "**/*.pyc"]
}
```

- [ ] **Step 5: `terraform validate` + conferir que o zip realmente não carrega `__pycache__`**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && terraform validate && rm -f lambda_payload.zip && terraform plan -target=data.archive_file.lambda -out=/tmp/plan_lambda_zip 2>&1 | tail -20 && unzip -l lambda_payload.zip`
Expected: `Success! The configuration is valid.`, o plan roda sem erro, e `unzip -l` não lista nenhum arquivo dentro de `__pycache__/` nem `.pyc`.

- [ ] **Step 6: Reescrever `invoke.py` inteiro**

```python
import os
import sys
import time
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import EventStreamError

# read_timeout alto: um turno pode encadear varias tools (CEP, cotacao, pedido).
client = boto3.client(
    "bedrock-agent-runtime",
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    config=Config(connect_timeout=10, read_timeout=120, retries={"max_attempts": 2}),
)

agent_id = os.environ.get("AGENT_ID")
alias_id = os.environ.get("ALIAS_ID")
if not agent_id or not alias_id:
    sys.exit(
        "Defina AGENT_ID e ALIAS_ID antes de rodar (nao ha default: o alias e recriado a cada "
        "deploy). Ex.:\n"
        "  AGENT_ID=$(terraform output -raw agent_id) "
        "ALIAS_ID=$(terraform output -raw agent_alias_id) python3 invoke.py 'oi, quero fazer um pedido'"
    )
session_id = sys.argv[2] if len(sys.argv) > 2 else f"cli-{uuid.uuid4().hex[:8]}"

# Erros transientes do Bedrock que valem retentar (a propria API pede "try again").
TRANSIENTES = ("dependencyFailedException", "throttlingException", "modelTimeout")


def responder(texto):
    resp = client.invoke_agent(
        agentId=agent_id, agentAliasId=alias_id, sessionId=session_id, inputText=texto
    )
    partes = [
        event["chunk"]["bytes"].decode()
        for event in resp["completion"]
        if "chunk" in event
    ]
    return "".join(partes)


texto = sys.argv[1]
for tentativa in range(3):
    try:
        sys.stdout.write(responder(texto))
        break
    except EventStreamError as erro:
        if tentativa < 2 and any(t in str(erro) for t in TRANSIENTES):
            time.sleep(2 * (tentativa + 1))
            continue
        raise

print(f"\n[session: {session_id}]")
```

- [ ] **Step 7: Conferir a falha clara sem AWS**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && unset AGENT_ID ALIAS_ID; python3 invoke.py "oi"; echo "exit code: $?"`
Expected: imprime a mensagem pedindo `AGENT_ID`/`ALIAS_ID` e sai com código diferente de 0 — não tenta chamar a AWS.

- [ ] **Step 8: Atualizar `README.md`**

Old (intro, linha 5):
```
Agente de delivery no Amazon Bedrock: **2 lojas**, **~118 itens** em 11 categorias, pizzas **meio a meio** com borda e tamanho, **combos**, **salgados vendidos por kg** (pedidos em gramas), observações por item e por pedido, horários de funcionamento por loja, janelas de disponibilidade por item e frete por loja. Foundation model **Amazon Nova Lite**; a lógica de negócio roda num action group Lambda em Python (stdlib apenas).
```

New:
```
Agente de delivery no Amazon Bedrock: **2 lojas**, **~118 itens** em 11 categorias, pizzas **meio a meio** com borda e tamanho, **combos**, **salgados vendidos por kg** (pedidos em gramas), observações por item e por pedido, horários de funcionamento por loja, janelas de disponibilidade por item e frete por loja. Foundation model **Amazon Nova Pro**; a lógica de negócio roda num action group Lambda em Python (stdlib apenas).
```

Old (tabela de arquitetura, linha "agent.tf"):
```
| `agent.tf` | O agente, o action group e as 5 funções (schema) |
```

New:
```
| `agent.tf` | O agente, o action group e as 9 funções (schema) |
```

Old (seção "Funções do action group" inteira, linhas 29-39):
```
### Funções do action group

1. `consultar_cardapio(categoria?, loja?)` — sem categoria, lista as categorias; com categoria, os itens (filtra por loja).
2. `listar_lojas()` — as 2 lojas com endereço, horário, se estão abertas agora e frete.
3. `adicionar_itens(itens, loja?)` — adiciona itens ao carrinho e devolve o carrinho com preços, a loja e se ela está aberta. Se a loja não for informada, escolhe automaticamente uma loja **aberta** que tenha os itens (e avisa se só houver loja fechada).
4. `ver_carrinho()` — mostra o que já foi escolhido, com preços.
5. `limpar_carrinho()` — esvazia o carrinho.
6. `revisar_pedido(cep)` — resumo final com frete e total, **sem registrar**.
7. `finalizar_pedido(cep, nome_cliente, observacoes?)` — revalida o carrinho, grava o pedido como log estruturado no CloudWatch (não é um registro consultável fora da conversa) e gera o número.

O carrinho fica em `sessionAttributes`, que o Bedrock mantém entre os turnos — a Lambda é a dona dos itens, então nada se perde na conversa. As funções **recusam** com motivo explicado: loja fechada, item fora do horário, item de outra loja, ou CEP inválido.
```

New:
```
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
```

Inserir uma nova seção "## Persistência" logo após a seção "## Modelo" (antes de "## Deploy"):

```
## Persistência

Este projeto **não usa banco de dados nem fila/notificação externa** (decisão de escopo, não lacuna): todo o estado do pedido vive em `sessionAttributes`, mantido pelo Bedrock durante a conversa — uma sessão nova começa com carrinho vazio. `finalizar_pedido` grava o pedido completo como uma linha de JSON estruturado no CloudWatch Logs (evento `pedido_finalizado`), e o `PED-...` retornado é a referência para achar essa linha nos logs — não é um registro consultável em nenhum sistema, nem sobrevive fora da sessão que o gerou.
```

- [ ] **Step 9: `terraform validate`**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 10: Rodar a suite inteira (nada de Python mudou nesta Task, mas confirma que nada quebrou)**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/ -v`
Expected: todos passam.

- [ ] **Step 11: Commit**

```bash
git add agent.tf lambda.tf invoke.py README.md
git commit -m "$(cat <<'EOF'
chore: corrigir schema, TTL, empacotamento da Lambda, invoke.py e documentacao

"salgados" estava ausente do enum de categorias em agent.tf; o campo obs nao
tinha exemplo (o modelo tinha que produzir 4 campos vazios sem nunca ter
visto isso); TTL de 600s evaporava o carrinho em qualquer pausa razoavel de
conversa (sobe para 3600s, o teto aceito e 5400s); o zip da Lambda incluia
__pycache__; invoke.py tinha AGENT_ID/ALIAS_ID hardcoded que apodrecem a cada
deploy (alias e recriado) e regiao fixa. README corrigido: Nova Lite -> Nova
Pro, contagem de funcoes (7 -> 9) e nova secao explicando a decisao de nao
usar banco de dados.
EOF
)"
```

---

### Task 4: Completar a suite de testes

As Tasks 0–2 já deixam uma suite pytest cobrindo a maior parte da lógica corrigida. Esta Task fecha os gaps de cobertura que a avaliação pediu explicitamente e ainda não têm teste dedicado (parse_itens com `qtd` ausente vs. inválida em conjunto, fluxo de carrinho ponta-a-ponta com remoção/alteração/finalização dupla), e documenta como rodar tudo no README.

**Files:**
- Modify: `tests/test_carrinho.py` (teste de fluxo completo)
- Modify: `tests/test_pedido.py` (casos de borda que ainda faltam)
- Modify: `README.md` (seção "Testes")

**Interfaces:** nenhuma nova — só testes e documentação.

- [ ] **Step 1: Adicionar o teste de fluxo completo em `tests/test_carrinho.py`**

```python
def test_fluxo_completo_adicionar_remover_alterar_finalizar_2x(monkeypatch, capsys):
    mock_cep_valido(monkeypatch)
    monkeypatch.setattr(geo, "agora", lambda: MOMENTO_ABERTO)
    session_attrs = {}

    r1 = carrinho.adicionar_itens({"itens": "hb01|2 ; bb01|1"}, session_attrs)
    assert r1["sucesso"] is True
    assert r1["quantidade_itens"] == 3
    assert len(r1["itens"]) == 2

    r2 = carrinho.adicionar_itens({"itens": "pz01|1|media"}, session_attrs)
    assert r2["sucesso"] is True
    assert len(r2["itens"]) == 3

    r3 = carrinho.remover_item({"numero": 2}, session_attrs)  # remove bb01
    assert r3["sucesso"] is True
    assert len(r3["itens"]) == 2

    r4 = carrinho.alterar_quantidade({"numero": "1", "quantidade": "5"}, session_attrs)
    assert r4["sucesso"] is True
    assert r4["itens"][0]["qtd"] == 5

    r5 = carrinho.finalizar_pedido({"cep": "01310100", "nome_cliente": "Bia"}, session_attrs)
    assert r5["sucesso"] is True
    assert "ja_finalizado" not in r5
    primeiro_id = r5["pedido_id"]
    capsys.readouterr()  # limpa o log do primeiro finalizar

    r6 = carrinho.finalizar_pedido({"cep": "01310100", "nome_cliente": "Bia"}, session_attrs)
    assert r6["sucesso"] is True
    assert r6["ja_finalizado"] is True
    assert r6["pedido_id"] == primeiro_id
    assert capsys.readouterr().out == ""  # 2a chamada nao gera novo log
```

- [ ] **Step 2: Adicionar os casos de borda restantes em `tests/test_pedido.py`**

```python
def test_parse_itens_varios_itens_no_mesmo_texto():
    itens, erro = pedido.parse_itens("bb01|3 ; hb01|2 ; pz04|1|grande|catupiry|pz01")
    assert erro is None
    assert [i["id"] for i in itens] == ["bb01", "hb01", "pz04"]
    assert itens[2]["meio_a_meio"] == ["pz04", "pz01"]


def test_parse_itens_ignora_blocos_vazios():
    itens, erro = pedido.parse_itens("bb01|1 ; ; hb01|1")
    assert erro is None
    assert len(itens) == 2


def test_parse_itens_id_vazio_e_ignorado():
    itens, erro = pedido.parse_itens("|1")
    assert erro is None
    assert itens == []
```

- [ ] **Step 3: Rodar a suite inteira**

Run: `cd /Users/leomarzeuski/Projects/bedrock-agent-pedidos && ./.venv/bin/python -m pytest tests/ -v`
Expected: todos passam (conferir a contagem total no resumo final do pytest).

- [ ] **Step 4: Adicionar seção "Testes" ao `README.md`** (inserir antes de "## Custo")

```
## Testes

Suite pytest cobrindo `pedido.py`, `geo.py`, `carrinho.py` e `handler.py` — sem rede nem AWS (CEP é mockado, horário é injetado via `momento`/`geo.agora`).

\`\`\`bash
source .venv/bin/activate && pip install -r requirements-dev.txt
pytest tests/ -v
\`\`\`
```

- [ ] **Step 5: Commit**

```bash
git add tests/ README.md
git commit -m "$(cat <<'EOF'
test: completar cobertura da suite pytest e documentar como rodar

Fecha os casos de borda pedidos na avaliacao 2026-07-11 que ainda nao tinham
teste dedicado: fluxo completo do carrinho (adicionar, remover, alterar,
finalizar 2x com ja_finalizado) e parsing de multiplos itens/blocos vazios.
Documenta no README como instalar e rodar a suite.
EOF
)"
```

---

## Entrega final

Depois do commit da Task 4, com a suite inteira passando:

1. Rodar `./.venv/bin/python -m pytest tests/ -v` uma última vez e confirmar a contagem de testes/passes no resumo.
2. Produzir um checklist **finding → status** cobrindo os 44 achados de `docs/revisao-2026-07-11.findings.json` (usar o apêndice da seção 6 de `docs/avaliacao-2026-07-11.md` como lista-base), classificando cada um como:
   - **corrigido** — implementado exatamente como recomendado;
   - **adaptado** — implementado diferente do recomendado (linkar a Task e explicar o porquê, ex.: a lista de categorias em `agent.tf:30` foi corrigida no literal, não via `locals`/`templatefile`, ver nota da Task 3 Step 1);
   - **pulei porque X** — não implementado nesta fase, com o motivo (ex.: pertence à Fase 2/3, ou é infra transversal fora do que as Tarefas 0–4 pediram: `iam.tf:35` trimprefix, `versions.tf:1` backend remoto, `agent.tf:117` alias `-replace`).
3. Listar o que fica para a Fase 2 (catálogo dinâmico, `buscar_item`, modificadores genéricos) e Fase 3 (WhatsApp, status de pedido, pagamento), sem implementá-las.
