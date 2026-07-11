"""Horarios de funcionamento, disponibilidade de itens, consulta de CEP e frete.

Sem coordenadas ou distancia: o CEP e apenas validado (endereco via ViaCEP) e o
frete e fixo por loja.
"""

import json
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


def loja_aberta(loja, momento=None):
    """True se a loja esta dentro de alguma faixa de funcionamento agora."""
    momento = momento or agora()
    faixas = loja["horarios"].get(momento.weekday(), [])
    atual = momento.hour * 60 + momento.minute
    return any(_minutos(abre) <= atual <= _minutos(fecha) for abre, fecha in faixas)


def item_disponivel(item, momento=None):
    """True se o item nao tem janela de horario ou se estamos dentro dela."""
    de, ate = item.get("disponivel_de"), item.get("disponivel_ate")
    if not de or not ate:
        return True
    momento = momento or agora()
    atual = momento.hour * 60 + momento.minute
    return _minutos(de) <= atual <= _minutos(ate)


# ---------------------------------------------------------------- CEP

def _get_json(url, timeout=5):
    """GET simples que devolve JSON como dict, ou None em qualquer falha."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agente-pedidos-estudo"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def consultar_cep(cep):
    """Valida o CEP e retorna o endereco (via ViaCEP).

    {"valido": True, "endereco": {...}} ou {"valido": False, "erro": "..."}.
    """
    digitos = "".join(c for c in str(cep) if c.isdigit())
    if len(digitos) != 8:
        return {"valido": False, "erro": "CEP deve conter 8 digitos"}

    via = _get_json(f"https://viacep.com.br/ws/{digitos}/json/")
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


# ---------------------------------------------------------------- frete

def frete_da_loja(loja, subtotal=0.0):
    """Frete fixo da loja, gratis a partir do valor configurado."""
    gratis = subtotal >= loja["frete_gratis_acima"]
    return {"frete": 0.0 if gratis else loja["frete_base"], "gratis": gratis}
