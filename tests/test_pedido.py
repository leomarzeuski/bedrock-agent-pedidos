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


@pytest.mark.parametrize("texto", ["duas", "2x", "1.5", "-2", "0", "", None, "abckg", "nan", "inf"])
def test_parse_quantidade_valores_invalidos_dao_erro_explicito(texto):
    valor, erro = pedido.parse_quantidade(texto)
    assert valor is None
    assert erro is not None


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
