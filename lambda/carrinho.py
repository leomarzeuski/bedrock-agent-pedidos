"""Carrinho persistido na sessao (sessionAttributes) e fechamento do pedido.

O carrinho e a fonte da verdade dos itens escolhidos: fica guardado entre os
turnos da conversa, entao nenhum item se perde. Cada funcao recebe o dict
session_attrs e o modifica no lugar (o handler o devolve ao Bedrock).
"""

import json
import uuid

import geo
import pedido
from dados import LOJAS, get_item

CHAVE = "carrinho"
CHAVE_ULTIMO_PEDIDO = "ultimo_pedido"


def _lojas_do_item(item_id):
    produto = get_item(item_id)
    return produto["lojas"] if produto else []


def _ids_do_item(pedido_item):
    """Ids envolvidos no item: o proprio e, se meio-a-meio, o 2o sabor."""
    ids = [pedido_item["id"]]
    for sabor in pedido_item.get("meio_a_meio") or []:
        if sabor not in ids:
            ids.append(sabor)
    return ids


def _lojas_efetivas(pedido_item):
    """Lojas que atendem o item inteiro. Para meio-a-meio, e a intersecao das
    lojas de todos os sabores (a pizza so existe onde os dois sabores existem)."""
    conjuntos = [set(_lojas_do_item(i)) for i in _ids_do_item(pedido_item)]
    return set.intersection(*conjuntos) if conjuntos else set()


def _lojas_candidatas(novos):
    """Lojas que vendem TODOS os itens do pedido (independente de estar aberta)."""
    return [lid for lid in LOJAS if all(lid in _lojas_efetivas(i) for i in novos)]


def _escolher_loja(novos, forcada):
    """Escolhe a loja para itens num carrinho vazio. Retorna (loja_id, erro).

    Prefere uma loja aberta que venda TODOS os itens. Se a pessoa indicou uma
    loja (forcada), respeita — desde que ela tenha os itens.
    """
    candidatas = _lojas_candidatas(novos)
    if not candidatas:
        return None, ("Esses itens nao estao todos na mesma loja. Um pedido e de uma loja so — "
                      "posso comecar por uma e depois fazer outro pedido.")
    if forcada:
        if forcada not in candidatas:
            return None, f"Esses itens nao estao disponiveis na loja {LOJAS[forcada]['nome']}."
        return forcada, None
    abertas = [lid for lid in candidatas if geo.loja_aberta(LOJAS[lid])]
    return (abertas or candidatas)[0], None


def _carregar(session_attrs):
    bruto = session_attrs.get(CHAVE)
    if bruto:
        try:
            return json.loads(bruto)
        except json.JSONDecodeError:
            pass
    return {"loja": None, "itens": []}


def _salvar(session_attrs, cart):
    session_attrs[CHAVE] = json.dumps(cart, ensure_ascii=False)


def _resumo(cart):
    """Carrinho precificado para exibir (linhas com preco + subtotal + numero
    da posicao, usado por remover_item/alterar_quantidade)."""
    linhas, subtotal, erro = pedido.precificar(cart["loja"], cart["itens"])
    if erro:
        return {"erro": erro}
    for numero, linha in enumerate(linhas, start=1):
        linha["numero"] = numero
    return {
        "loja": LOJAS[cart["loja"]]["nome"],
        "itens": linhas,
        "quantidade_itens": sum(l["qtd"] for l in linhas),
        "subtotal": subtotal,
    }


def _chave_item(it):
    """Assinatura de um item para decidir se e 'o mesmo' de outro (soma qtd em
    vez de duplicar linha)."""
    return (it["id"], it.get("tamanho"), it.get("borda"),
            tuple(it.get("meio_a_meio") or []), it.get("obs"))


def _mesclar_itens(existentes, novos):
    """Soma a quantidade de itens identicos (mesmo id/tamanho/borda/
    meio_a_meio/obs) em vez de duplicar a linha."""
    for novo in novos:
        chave_novo = _chave_item(novo)
        igual = next((it for it in existentes if _chave_item(it) == chave_novo), None)
        if igual:
            igual["qtd"] += novo["qtd"]
        else:
            existentes.append(novo)


def adicionar_itens(params, session_attrs):
    novos, erro = pedido.parse_itens(params.get("itens", ""))
    if erro:
        return {"sucesso": False, "erro": erro}
    if not novos:
        return {"sucesso": False, "erro": "Nenhum item informado"}
    for it in novos:
        for sabor in _ids_do_item(it):  # inclui os sabores do meio-a-meio
            if not get_item(sabor):
                return {"sucesso": False, "erro": f"Item inexistente: {sabor}"}

    forcada = (params.get("loja") or "").strip().upper() or None
    if forcada and forcada not in LOJAS:
        return {"sucesso": False, "erro": "Loja invalida. Escolha A ou B."}

    cart = _carregar(session_attrs)
    if cart["itens"]:
        # Carrinho ja tem loja: os novos itens (e uma loja forcada, se houver)
        # precisam ser dela — nunca ignorar em silencio.
        loja_id = cart["loja"]
        if forcada and forcada != loja_id:
            return {"sucesso": False,
                    "erro": (f"Seu carrinho ja esta com itens da {LOJAS[loja_id]['nome']}. Um pedido "
                             f"e de uma loja so: finalize ou limpe o carrinho antes de pedir da "
                             f"{LOJAS[forcada]['nome']}.")}
        fora = [get_item(i["id"])["nome"] for i in novos if loja_id not in _lojas_efetivas(i)]
        if fora:
            return {"sucesso": False,
                    "erro": (f"{', '.join(fora)} nao e da loja {LOJAS[loja_id]['nome']}, onde seu "
                             "carrinho esta. Um pedido e de uma loja so: posso finalizar ou limpar "
                             "o carrinho atual antes de trocar de loja.")}
    else:
        loja_id, erro = _escolher_loja(novos, forcada)
        if erro:
            return {"sucesso": False, "erro": erro}

    # Loja fechada: nao aceita pedido (nao monta carrinho que nao fecha).
    loja = LOJAS[loja_id]
    if not geo.loja_aberta(loja):
        candidatas = _lojas_candidatas(novos)
        abertas = [LOJAS[lid] for lid in candidatas if lid != loja_id and geo.loja_aberta(LOJAS[lid])]
        if abertas:
            nomes = ", ".join(l["nome"] for l in abertas)
            return {"sucesso": False, "loja_fechada": True, "loja": loja["nome"],
                    "horario": loja["horario_texto"],
                    "erro": (f"A {loja['nome']} esta fechada agora ({loja['horario_texto']}). Esses "
                             f"itens tambem tem na {nomes}, que esta aberta agora — quer pedir de la?")}
        return {"sucesso": False, "loja_fechada": True, "loja": loja["nome"],
                "horario": loja["horario_texto"],
                "erro": (f"A {loja['nome']} esta fechada agora ({loja['horario_texto']}). Esse item so "
                         "e vendido nela; nenhuma loja aberta agora tem esse item. So da pra pedir "
                         "quando ela reabrir.")}

    # Valida horario dos itens e precifica antes de guardar.
    _, _, erro = pedido.precificar(loja_id, novos)
    if erro:
        return {"sucesso": False, "erro": erro}

    cart["loja"] = loja_id
    _mesclar_itens(cart["itens"], novos)
    _salvar(session_attrs, cart)

    resultado = _resumo(cart)
    if "erro" in resultado:
        return {"sucesso": False,
                "erro": f"Item adicionado, mas o carrinho ficou invalido: {resultado['erro']}"}
    resultado["sucesso"] = True
    resultado["mensagem"] = "Itens adicionados. Deseja mais alguma coisa ou fechar o pedido?"
    return resultado


def ver_carrinho(session_attrs):
    cart = _carregar(session_attrs)
    if not cart["itens"]:
        return {"vazio": True, "mensagem": "Seu carrinho ainda esta vazio."}
    return _resumo(cart)


def remover_item(params, session_attrs):
    """Remove um item do carrinho pela posicao mostrada em ver_carrinho
    (campo 'numero' de cada linha, comecando em 1)."""
    cart = _carregar(session_attrs)
    if not cart["itens"]:
        return {"sucesso": False, "erro": "Carrinho vazio"}

    numero = params.get("numero")
    try:
        indice = int(numero) - 1
    except (TypeError, ValueError):
        return {"sucesso": False, "erro": f"Numero de item invalido: '{numero}'"}
    if indice < 0 or indice >= len(cart["itens"]):
        return {"sucesso": False,
                "erro": f"Nao existe item numero {numero}. O carrinho tem {len(cart['itens'])} item(ns)."}

    removido = cart["itens"].pop(indice)
    nome_removido = get_item(removido["id"])["nome"]

    if not cart["itens"]:
        session_attrs.pop(CHAVE, None)
        return {"sucesso": True, "mensagem": f"{nome_removido} removido. Carrinho vazio."}

    _salvar(session_attrs, cart)
    resultado = _resumo(cart)
    if "erro" in resultado:
        return {"sucesso": False,
                "erro": f"{nome_removido} removido, mas o carrinho ficou invalido: {resultado['erro']}"}
    resultado["sucesso"] = True
    resultado["mensagem"] = f"{nome_removido} removido."
    return resultado


def alterar_quantidade(params, session_attrs):
    """Altera a quantidade (ou, para itens por kg, os gramas) de um item ja
    no carrinho, pela posicao mostrada em ver_carrinho."""
    cart = _carregar(session_attrs)
    if not cart["itens"]:
        return {"sucesso": False, "erro": "Carrinho vazio"}

    numero = params.get("numero")
    try:
        indice = int(numero) - 1
    except (TypeError, ValueError):
        return {"sucesso": False, "erro": f"Numero de item invalido: '{numero}'"}
    if indice < 0 or indice >= len(cart["itens"]):
        return {"sucesso": False,
                "erro": f"Nao existe item numero {numero}. O carrinho tem {len(cart['itens'])} item(ns)."}

    nova_qtd, erro = pedido.parse_quantidade(params.get("quantidade"))
    if erro:
        return {"sucesso": False, "erro": erro}

    cart["itens"][indice]["qtd"] = nova_qtd
    _salvar(session_attrs, cart)

    resultado = _resumo(cart)
    if "erro" in resultado:
        return {"sucesso": False,
                "erro": f"Quantidade nao pode ser alterada: {resultado['erro']}"}
    resultado["sucesso"] = True
    resultado["mensagem"] = "Quantidade atualizada."
    return resultado


def limpar_carrinho(session_attrs):
    session_attrs.pop(CHAVE, None)
    return {"sucesso": True, "mensagem": "Carrinho esvaziado."}


def revisar_pedido(params, session_attrs):
    """Resumo final com frete e total para um CEP, sem registrar."""
    cart = _carregar(session_attrs)
    if not cart["itens"]:
        return {"sucesso": False, "erro": "Carrinho vazio"}

    loja = LOJAS[cart["loja"]]
    if not geo.loja_aberta(loja):
        return {"sucesso": False,
                "erro": f"A loja {loja['nome']} esta fechada agora. Horario: {loja['horario_texto']}"}

    endereco = geo.consultar_cep(params.get("cep", ""))
    if not endereco.get("valido"):
        return {"sucesso": False, "erro": endereco.get("erro", "CEP invalido")}
    if not geo.area_atendida(loja, endereco["endereco"]):
        return {"sucesso": False,
                "erro": (f"Esse CEP fica fora da area de entrega da {loja['nome']} "
                         f"(atende {loja['cidade']}/{loja['uf']}). Nao da pra entregar ai.")}

    linhas, subtotal, erro = pedido.precificar(cart["loja"], cart["itens"])
    if erro:
        return {"sucesso": False, "erro": erro}

    entrega = geo.frete_da_loja(loja, subtotal)
    total = pedido._dinheiro(subtotal) + pedido._dinheiro(entrega["frete"])
    return {
        "sucesso": True,
        "loja": loja["nome"],
        "endereco_entrega": endereco["endereco"],
        "itens": linhas,
        "subtotal": subtotal,
        "frete": entrega["frete"],
        "frete_gratis": entrega["gratis"],
        "total": float(total),
    }


def finalizar_pedido(params, session_attrs):
    """Revalida o carrinho, registra o pedido no log e esvazia o carrinho.

    Sem banco de dados: "registrar" e gravar o pedido completo como uma linha
    de JSON estruturado no CloudWatch Logs (evento pedido_finalizado). O
    numero PED-... e so uma referencia para achar essa linha nos logs — nao e
    um registro consultavel em nenhum sistema, nem sobrevive fora da sessao.

    Se chamado de novo (retry comum do Nova) com o carrinho ja vazio, devolve
    o ultimo pedido finalizado nesta sessao em vez de erro, com a flag
    ja_finalizado, no lugar de "Carrinho vazio".
    """
    cart = _carregar(session_attrs)
    if not cart["itens"] and CHAVE_ULTIMO_PEDIDO in session_attrs:
        ultimo = json.loads(session_attrs[CHAVE_ULTIMO_PEDIDO])
        ultimo["ja_finalizado"] = True
        return ultimo

    resultado = revisar_pedido(params, session_attrs)
    if not resultado.get("sucesso"):
        return resultado

    pedido_id = f"PED-{uuid.uuid4().hex[:8].upper()}"
    resultado["pedido_id"] = pedido_id
    resultado["cliente"] = params.get("nome_cliente")
    obs = (params.get("observacoes") or "").strip()
    if obs:
        resultado["observacoes"] = obs

    print(json.dumps({
        "evento": "pedido_finalizado",
        "pedido_id": pedido_id,
        "loja": resultado["loja"],
        "itens": resultado["itens"],
        "endereco": resultado["endereco_entrega"],
        "subtotal": resultado["subtotal"],
        "frete": resultado["frete"],
        "frete_gratis": resultado["frete_gratis"],
        "total": resultado["total"],
        "cliente": resultado["cliente"],
        "observacoes": resultado.get("observacoes"),
        "timestamp": geo.agora().isoformat(),
    }, ensure_ascii=False))

    session_attrs[CHAVE_ULTIMO_PEDIDO] = json.dumps(resultado, ensure_ascii=False)
    session_attrs.pop(CHAVE, None)
    return resultado
