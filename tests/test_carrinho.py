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
        {"cep": "01310100", "nome_cliente": "Ana", "observacoes": "deixar na portaria"},
        session_attrs)

    assert resultado["sucesso"] is True
    assert resultado["pedido_id"].startswith("PED-")

    saida = capsys.readouterr().out.strip().splitlines()
    linha = json.loads(saida[-1])
    assert linha["evento"] == "pedido_finalizado"
    assert linha["pedido_id"] == resultado["pedido_id"]
    assert linha["cliente"] == "Ana"
    assert linha["total"] == resultado["total"]
    assert linha["loja"] == resultado["loja"]
    assert linha["subtotal"] == resultado["subtotal"]
    assert linha["frete"] == resultado["frete"]
    assert linha["observacoes"] == "deixar na portaria"


def test_finalizar_pedido_loga_observacoes_como_none_quando_ausente(monkeypatch, capsys):
    mock_cep_valido(monkeypatch)
    session_attrs = _carrinho_com_pizza(monkeypatch)

    carrinho.finalizar_pedido(
        {"cep": "01310100", "nome_cliente": "Ana"}, session_attrs)

    saida = capsys.readouterr().out.strip().splitlines()
    linha = json.loads(saida[-1])
    assert linha["observacoes"] is None


def test_finalizar_pedido_guarda_ultimo_pedido_na_sessao_e_esvazia_carrinho(monkeypatch):
    mock_cep_valido(monkeypatch)
    session_attrs = _carrinho_com_pizza(monkeypatch)

    resultado = carrinho.finalizar_pedido(
        {"cep": "01310100", "nome_cliente": "Ana"}, session_attrs)

    assert carrinho.CHAVE not in session_attrs
    assert carrinho.CHAVE_ULTIMO_PEDIDO in session_attrs
    salvo = json.loads(session_attrs[carrinho.CHAVE_ULTIMO_PEDIDO])
    assert salvo["pedido_id"] == resultado["pedido_id"]


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
