"""Entrada da Lambda do action group. Faz o dispatch para as funcoes do agente.

Funcoes: consultar_cardapio, listar_lojas, validar_cep, cotar_pedido, criar_pedido.
"""

import json

import geo
import pedido
from dados import CARDAPIO, CATEGORIAS, LOJAS


def consultar_cardapio(params):
    """Sem categoria: lista as categorias. Com categoria: itens da categoria,
    opcionalmente filtrados pela loja."""
    categoria = (params.get("categoria") or "").strip().lower()
    loja_id = (params.get("loja") or "").strip().upper() or None

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
        registro = {
            "id": it["id"],
            "nome": it["nome"],
            "descricao": it["descricao"],
            "lojas": it["lojas"],
            "disponivel_agora": geo.item_disponivel(it),
        }
        if it["tipo"] == "pizza":
            registro["tamanhos"] = it["tamanhos"]
            registro["meio_a_meio"] = True
        elif it["tipo"] == "combo":
            registro["preco"] = it["preco"]
            registro["inclui"] = it["inclui"]
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


_FUNCOES = {
    "consultar_cardapio": lambda p: consultar_cardapio(p),
    "listar_lojas": lambda p: listar_lojas(),
    "validar_cep": lambda p: geo.consultar_cep(p.get("cep", "")),
    "cotar_pedido": lambda p: pedido.cotar_pedido(p),
    "criar_pedido": lambda p: pedido.criar_pedido(p),
}


def lambda_handler(event, context):
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    executor = _FUNCOES.get(function)
    result = executor(params) if executor else {"erro": f"Funcao desconhecida: {function}"}

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup"),
            "function": function,
            "functionResponse": {
                "responseBody": {"TEXT": {"body": json.dumps(result, ensure_ascii=False)}}
            },
        },
        "sessionAttributes": event.get("sessionAttributes", {}),
        "promptSessionAttributes": event.get("promptSessionAttributes", {}),
    }
