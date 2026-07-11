"""Parsing e precificacao de itens — o motor de precos do carrinho.

Precos: pizza = tamanho escolhido (meio-a-meio = sabor mais caro) + borda;
combo = preco fixo; demais = preco do item. Nao registra nada — quem monta e
fecha o pedido e o modulo carrinho.
"""

import geo
from dados import BORDAS, get_item


def parse_quantidade(texto):
    """Converte o texto de uma quantidade num inteiro positivo.

    Aceita numero puro (unidades ou, para itens por peso, gramas: "3", "500")
    ou peso com sufixo ("500g", "1kg" -> 1000g; aceita virgula decimal, mas
    so quando ha sufixo kg: "1,5kg" -> 1500). Sem sufixo kg (numero puro ou
    sufixo "g"), a quantidade tem que ser um inteiro — casas decimais dao
    erro. Retorna (valor, erro): erro e None se valido, e nesse caso valor e
    sempre um inteiro > 0; caso contrario valor e None.
    """
    bruto = str(texto if texto is not None else "").strip().lower().replace(",", ".")
    if not bruto:
        return None, "Quantidade nao informada"

    if bruto.endswith("kg"):
        numero, fator, aceita_decimal = bruto[:-2].strip(), 1000, True
    elif bruto.endswith("g"):
        numero, fator, aceita_decimal = bruto[:-1].strip(), 1, False
    else:
        numero, fator, aceita_decimal = bruto, 1, False

    try:
        bruto_float = float(numero)
    except ValueError:
        return None, f"Quantidade invalida: '{texto}'. Informe um numero, ex.: '2' ou, para itens por peso, '500g'"

    if not aceita_decimal and bruto_float != int(bruto_float):
        return None, f"Quantidade invalida: '{texto}'. Informe um numero, ex.: '2' ou, para itens por peso, '500g'"

    valor = round(bruto_float * fator)
    if valor <= 0:
        return None, f"Quantidade deve ser maior que zero: '{texto}'"
    return valor, None


def parse_itens(texto):
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
    obs = (pedido_item.get("obs") or "").strip()

    # Salgados sao vendidos por peso: aqui a "quantidade" (qtd) e em gramas.
    if produto["tipo"] == "peso":
        gramas = qtd
        minimo = produto.get("minimo_g", 0)
        if gramas < minimo:
            return None, f"{produto['nome']} tem pedido minimo de {minimo}g (voce pediu {gramas}g)"
        preco = produto["preco_por_kg"] * gramas / 1000
        linha = {
            "item": f"{produto['nome']} ({gramas}g)",
            "qtd": 1,
            "gramas": gramas,
            "preco_kg": produto["preco_por_kg"],
            "subtotal": round(preco, 2),
        }
        if obs:
            linha["obs"] = obs
        return linha, None

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
    if obs:
        linha["obs"] = obs
    return linha, None


def precificar(loja_id, itens):
    """Valida e precifica os itens na loja. Retorna (linhas, subtotal, erro).

    Valida existencia do item, se e vendido na loja e se esta na janela de horario.
    """
    linhas = []
    subtotal = 0.0
    for pedido_item in itens:
        produto = get_item(pedido_item.get("id"))
        if not produto:
            return None, 0.0, f"Item inexistente: {pedido_item.get('id')}"
        if loja_id not in produto["lojas"]:
            return None, 0.0, f"{produto['nome']} nao esta disponivel nesta loja"
        if not geo.item_disponivel(produto):
            return None, 0.0, (f"{produto['nome']} so esta disponivel das "
                               f"{produto['disponivel_de']} as {produto['disponivel_ate']}")
        linha, erro = _monta_linha(produto, pedido_item, loja_id)
        if erro:
            return None, 0.0, erro
        linhas.append(linha)
        subtotal += linha["subtotal"]
    return linhas, round(subtotal, 2), None
