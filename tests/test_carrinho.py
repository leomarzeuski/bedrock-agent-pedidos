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
