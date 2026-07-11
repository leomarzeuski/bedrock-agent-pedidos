"""Montagem, cotacao e registro de um pedido.

Regras (todas bloqueiam o pedido com erro explicativo):
- a loja precisa existir e estar aberta no horario atual;
- o CEP precisa ser valido;
- cada item precisa existir, ser vendido naquela loja e estar na janela de horario.

Precos: pizza = tamanho escolhido (meio-a-meio = sabor mais caro) + borda;
combo = preco fixo; demais = preco do item. Frete e fixo por loja.

cotar_pedido calcula tudo sem registrar (para montar o resumo); criar_pedido
faz a mesma validacao e gera o numero do pedido.
"""

import uuid

import geo
from dados import BORDAS, LOJAS, get_item


def _parse_itens(texto):
    """Converte o texto do pedido em lista de itens.

    Itens separados por ';', campos por '|' na ordem:
    id|qtd|tamanho|borda|meio_a_meio|obs. Apenas o id e obrigatorio;
    tamanho/borda/meio_a_meio valem so para pizza (meio_a_meio = id do 2o sabor).
    Ex.: "bb05|3 ; hb01|2 ; pz04|1|grande|catupiry|pz01|caprichar no queijo"
    """
    itens = []
    for bloco in texto.split(";"):
        campos = [c.strip() for c in bloco.split("|")]
        item_id = campos[0]
        if not item_id:
            continue
        item = {"id": item_id}
        qtd = campos[1] if len(campos) > 1 else ""
        item["qtd"] = int(qtd) if qtd.isdigit() else 1
        if len(campos) > 2 and campos[2]:
            item["tamanho"] = campos[2]
        if len(campos) > 3 and campos[3]:
            item["borda"] = campos[3]
        if len(campos) > 4 and campos[4]:
            item["meio_a_meio"] = [item_id, campos[4]]
        if len(campos) > 5 and campos[5]:
            item["obs"] = campos[5]
        itens.append(item)
    return itens


def _preco_pizza(produto, tamanho, meio_a_meio, loja_id):
    """Retorna (preco_base, [sabores]) ou (None, mensagem_erro)."""
    if tamanho not in produto["tamanhos"]:
        opcoes = ", ".join(produto["tamanhos"])
        return None, f"Tamanho invalido para {produto['nome']}. Opcoes: {opcoes}"

    precos = [produto["tamanhos"][tamanho]]
    sabores = [produto["nome"]]

    for outro_id in meio_a_meio or []:
        if outro_id == produto["id"]:
            continue
        outro = get_item(outro_id)
        if not outro or outro.get("tipo") != "pizza":
            return None, f"Sabor de pizza invalido: {outro_id}"
        if loja_id not in outro["lojas"]:
            return None, f"O sabor {outro['nome']} nao esta disponivel nesta loja"
        if tamanho not in outro["tamanhos"]:
            return None, f"O sabor {outro['nome']} nao tem o tamanho {tamanho}"
        precos.append(outro["tamanhos"][tamanho])
        sabores.append(outro["nome"])

    # Meio-a-meio cobra pelo sabor mais caro.
    return max(precos), sabores


def _monta_linha(produto, pedido_item, loja_id):
    """Retorna (linha, erro). linha = dict com item/qtd/precos; erro = str|None."""
    qtd = int(pedido_item.get("qtd", 1))
    if qtd < 1:
        return None, f"Quantidade invalida para {produto['nome']}"

    if produto["tipo"] == "pizza":
        tamanho = (pedido_item.get("tamanho") or "").strip().lower()
        preco, sabores = _preco_pizza(produto, tamanho, pedido_item.get("meio_a_meio"), loja_id)
        if preco is None:
            return None, sabores  # sabores carrega a mensagem de erro
        borda = (pedido_item.get("borda") or "sem").strip().lower()
        if borda not in BORDAS:
            return None, f"Borda invalida. Opcoes: {', '.join(BORDAS)}"
        preco += BORDAS[borda]
        nome = f"Pizza {'/'.join(sabores)} ({tamanho}"
        nome += f", borda {borda})" if borda != "sem" else ")"
    elif produto["tipo"] == "combo":
        preco = produto["preco"]
        nome = f"{produto['nome']} (combo)"
    else:
        preco = produto["preco"]
        nome = produto["nome"]

    linha = {
        "item": nome,
        "qtd": qtd,
        "preco_unitario": round(preco, 2),
        "subtotal": round(preco * qtd, 2),
    }
    obs = (pedido_item.get("obs") or "").strip()
    if obs:
        linha["obs"] = obs
    return linha, None


def _montar(params):
    """Valida e precifica o pedido. Retorna o resumo (sem numero) ou um erro."""
    loja_id = (params.get("loja") or "").strip().upper()
    loja = LOJAS.get(loja_id)
    if not loja:
        return {"sucesso": False, "erro": f"Loja invalida. Escolha entre: {', '.join(LOJAS)}"}

    if not geo.loja_aberta(loja):
        return {"sucesso": False,
                "erro": f"A loja {loja['nome']} esta fechada agora. Horario: {loja['horario_texto']}"}

    endereco = geo.consultar_cep(params.get("cep", ""))
    if not endereco.get("valido"):
        return {"sucesso": False, "erro": endereco.get("erro", "CEP invalido")}

    itens = _parse_itens(params.get("itens", ""))
    if not itens:
        return {"sucesso": False, "erro": "Pedido sem itens"}

    resumo = []
    subtotal = 0.0
    for pedido_item in itens:
        produto = get_item(pedido_item.get("id"))
        if not produto:
            return {"sucesso": False, "erro": f"Item inexistente: {pedido_item.get('id')}"}
        if loja_id not in produto["lojas"]:
            return {"sucesso": False,
                    "erro": f"{produto['nome']} nao esta disponivel na loja {loja['nome']}"}
        if not geo.item_disponivel(produto):
            return {"sucesso": False,
                    "erro": (f"{produto['nome']} so esta disponivel das "
                             f"{produto['disponivel_de']} as {produto['disponivel_ate']}")}

        linha, erro = _monta_linha(produto, pedido_item, loja_id)
        if erro:
            return {"sucesso": False, "erro": erro}
        resumo.append(linha)
        subtotal += linha["subtotal"]

    entrega = geo.frete_da_loja(loja, subtotal)
    resultado = {
        "sucesso": True,
        "loja": loja["nome"],
        "cliente": params.get("nome_cliente"),
        "endereco_entrega": endereco["endereco"],
        "itens": resumo,
        "subtotal": round(subtotal, 2),
        "frete": entrega["frete"],
        "frete_gratis": entrega["gratis"],
        "total": round(subtotal + entrega["frete"], 2),
    }
    observacoes = (params.get("observacoes") or "").strip()
    if observacoes:
        resultado["observacoes"] = observacoes
    return resultado


def cotar_pedido(params):
    """Calcula o preco exato do pedido (para o resumo) sem registrar."""
    resultado = _montar(params)
    if resultado.get("sucesso"):
        resultado["cotacao"] = True
    return resultado


def criar_pedido(params):
    """Registra o pedido, gerando o numero. Revalida tudo antes."""
    resultado = _montar(params)
    if resultado.get("sucesso"):
        resultado["pedido_id"] = f"PED-{uuid.uuid4().hex[:8].upper()}"
    return resultado
