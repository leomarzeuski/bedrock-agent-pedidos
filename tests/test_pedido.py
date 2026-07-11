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
