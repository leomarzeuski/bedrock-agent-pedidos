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
