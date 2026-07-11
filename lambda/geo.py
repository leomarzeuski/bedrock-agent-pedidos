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
