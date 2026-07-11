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
