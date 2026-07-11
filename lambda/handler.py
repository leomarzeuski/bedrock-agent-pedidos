"""Entrada da Lambda do action group. Faz o dispatch para as funcoes do agente.

Funcoes: consultar_cardapio, listar_lojas, adicionar_itens, ver_carrinho,
remover_item, alterar_quantidade, limpar_carrinho, revisar_pedido,
finalizar_pedido. As funcoes de carrinho leem e escrevem o carrinho em
sessionAttributes, que o Bedrock mantem entre os turnos.
"""

import json

import carrinho
import geo
from dados import CARDAPIO, CATEGORIAS, LOJAS


def _normalizar(texto):
    """minusculo, sem acento, sem espaco nas bordas — para comparar nomes de loja."""
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower()


def _resolver_loja(texto):
    """Aceita 'A'/'B' ou o nome da loja (case/acento insensivel). Retorna o
    id ou None se nao reconhecer."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if texto.upper() in LOJAS:
        return texto.upper()
    normalizado = _normalizar(texto)
    for loja in LOJAS.values():
        if _normalizar(loja["nome"]) == normalizado:
            return loja["id"]
    return None


def consultar_cardapio(params):
    """Sem categoria: lista as categorias. Com categoria: itens da categoria,
    opcionalmente filtrados pela loja (aceita id A/B ou o nome da loja)."""
    categoria = (params.get("categoria") or "").strip().lower()
    loja_bruta = (params.get("loja") or "").strip()
    loja_id = None
    if loja_bruta:
        loja_id = _resolver_loja(loja_bruta)
        if not loja_id:
            return {"erro": f"Loja invalida: '{loja_bruta}'. Use listar_lojas para ver as lojas existentes."}

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
        # Com filtro de loja, disponibilidade considera SO a loja filtrada
        # (senao "disponivel_agora" fica contraditorio com adicionar_itens).
        lojas_relevantes = [loja_id] if loja_id else it["lojas"]
        na_janela = geo.item_disponivel(it)
        loja_aberta_agora = any(geo.loja_aberta(LOJAS[l]) for l in lojas_relevantes)
        registro = {
            "id": it["id"],
            "nome": it["nome"],
            "descricao": it["descricao"],
            "lojas": it["lojas"],
            "disponivel_agora": na_janela and loja_aberta_agora,
        }
        if not registro["disponivel_agora"]:
            lojas_txt = "; ".join(f"{LOJAS[l]['nome']} ({LOJAS[l]['horario_texto']})"
                                  for l in lojas_relevantes)
            if not na_janela:
                registro["obs_disponibilidade"] = (
                    f"disponivel so das {it['disponivel_de']} as {it['disponivel_ate']}; "
                    f"vendido na {lojas_txt}")
            else:
                registro["obs_disponibilidade"] = f"vendido so na {lojas_txt}, fechada agora"
        if it["tipo"] == "pizza":
            registro["tamanhos"] = it["tamanhos"]
            registro["meio_a_meio"] = True
        elif it["tipo"] == "combo":
            registro["preco"] = it["preco"]
            registro["inclui"] = it["inclui"]
        elif it["tipo"] == "peso":
            registro["preco_por_kg"] = it["preco_por_kg"]
            registro["minimo_g"] = it["minimo_g"]
            registro["unidade"] = "kg (pedido em gramas)"
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


def lambda_handler(event, context):
    function = event.get("function", "")
    params = {p["name"]: p.get("value", "") for p in event.get("parameters", [])}
    session_attrs = dict(event.get("sessionAttributes") or {})

    try:
        if function == "consultar_cardapio":
            result = consultar_cardapio(params)
        elif function == "listar_lojas":
            result = listar_lojas()
        elif function == "adicionar_itens":
            result = carrinho.adicionar_itens(params, session_attrs)
        elif function == "ver_carrinho":
            result = carrinho.ver_carrinho(session_attrs)
        elif function == "remover_item":
            result = carrinho.remover_item(params, session_attrs)
        elif function == "alterar_quantidade":
            result = carrinho.alterar_quantidade(params, session_attrs)
        elif function == "limpar_carrinho":
            result = carrinho.limpar_carrinho(session_attrs)
        elif function == "revisar_pedido":
            result = carrinho.revisar_pedido(params, session_attrs)
        elif function == "finalizar_pedido":
            result = carrinho.finalizar_pedido(params, session_attrs)
        else:
            result = {"erro": f"Funcao desconhecida: {function}"}
    except Exception as exc:
        print(json.dumps({"evento": "erro_dispatch", "function": function, "erro": str(exc)},
                          ensure_ascii=False))
        result = {"erro": "Erro interno ao processar o pedido. Tente novamente."}

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup"),
            "function": function,
            "functionResponse": {
                "responseBody": {"TEXT": {"body": json.dumps(result, ensure_ascii=False)}}
            },
        },
        "sessionAttributes": session_attrs,
        "promptSessionAttributes": event.get("promptSessionAttributes", {}),
    }
