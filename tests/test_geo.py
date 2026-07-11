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
