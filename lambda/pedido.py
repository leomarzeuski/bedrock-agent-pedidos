"""Parsing e precificacao de itens — o motor de precos do carrinho.

Precos: pizza = tamanho escolhido (meio-a-meio = sabor mais caro) + borda;
combo = preco fixo; demais = preco do item. Dinheiro em Decimal com
arredondamento ROUND_HALF_UP em todo o calculo, convertido para float so na
saida (json nao serializa Decimal). Nao registra nada — quem monta e fecha o
pedido e o modulo carrinho.
"""

from decimal import Decimal, ROUND_HALF_UP

import geo
from dados import BORDAS, get_item

DUAS_CASAS = Decimal("0.01")


def _dinheiro(valor):
    """Converte numero (int/float/str) para Decimal com 2 casas, half-up."""
    return Decimal(str(valor)).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)


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
    tamanho/borda/meio_a_meio valem so para pizza (meio_a_meio = id do 2o
    sabor) — para os demais itens, texto nesses campos e preservado como
    observacao em vez de descartado. Obs junta tudo a partir do 5o campo
    (join com '|') para nao truncar observacoes que contenham '|'.
    Ex.: "bb05|3 ; hb01|2 ; pz04|1|grande|catupiry|pz01|caprichar no queijo"

    Retorna (itens, erro). Em caso de erro (ex.: quantidade invalida), itens
    e None.
    """
    itens = []
    for bloco in texto.split(";"):
        bloco = bloco.strip()
        if not bloco:
            continue
        campos = [c.strip() for c in bloco.split("|")]
        item_id = campos[0]
        if not item_id:
            continue

        campo_qtd = campos[1] if len(campos) > 1 and campos[1] else "1"
        qtd, erro = parse_quantidade(campo_qtd)
        if erro:
            return None, f"Item {item_id}: {erro}"

        item = {"id": item_id, "qtd": qtd}
        produto = get_item(item_id)

        tamanho = campos[2] if len(campos) > 2 else ""
        borda = campos[3] if len(campos) > 3 else ""
        segundo_sabor = campos[4] if len(campos) > 4 else ""
        obs = "|".join(campos[5:]) if len(campos) > 5 else ""

        if produto and produto.get("tipo") == "pizza":
            if tamanho:
                item["tamanho"] = tamanho
            if borda:
                item["borda"] = borda
            if segundo_sabor:
                item["meio_a_meio"] = [item_id, segundo_sabor]
        else:
            # Tamanho/borda/meio_a_meio nao se aplicam a este item: preserva
            # como observacao em vez de descartar (ex.: "hb01|2|sem picles"
            # nao pode sumir so porque o campo esta na posicao errada).
            perdidos = [c for c in (tamanho, borda, segundo_sabor) if c]
            if perdidos:
                obs = " | ".join(perdidos + ([obs] if obs else []))

        if obs:
            item["obs"] = obs
        itens.append(item)
    return itens, None


def _preco_pizza(produto, tamanho, meio_a_meio, loja_id):
    """Retorna (preco_base: Decimal, [sabores]) ou (None, mensagem_erro)."""
    if tamanho not in produto["tamanhos"]:
        opcoes = ", ".join(produto["tamanhos"])
        return None, f"Tamanho invalido para {produto['nome']}. Opcoes: {opcoes}"

    precos = [_dinheiro(produto["tamanhos"][tamanho])]
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
        precos.append(_dinheiro(outro["tamanhos"][tamanho]))
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
        preco = (_dinheiro(produto["preco_por_kg"]) * gramas / Decimal(1000)).quantize(
            DUAS_CASAS, rounding=ROUND_HALF_UP)
        linha = {
            "item": f"{produto['nome']} ({gramas}g)",
            "qtd": 1,
            "gramas": gramas,
            "preco_kg": float(_dinheiro(produto["preco_por_kg"])),
            "subtotal": float(preco),
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
        preco += _dinheiro(BORDAS[borda])
        nome = f"Pizza {'/'.join(sabores)} ({tamanho}"
        nome += f", borda {borda})" if borda != "sem" else ")"
    elif produto["tipo"] == "combo":
        preco = _dinheiro(produto["preco"])
        nome = f"{produto['nome']} (combo)"
    else:
        preco = _dinheiro(produto["preco"])
        nome = produto["nome"]

    subtotal = (preco * qtd).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)
    linha = {
        "item": nome,
        "qtd": qtd,
        "preco_unitario": float(preco),
        "subtotal": float(subtotal),
    }
    if obs:
        linha["obs"] = obs
    return linha, None


def precificar(loja_id, itens):
    """Valida e precifica os itens na loja. Retorna (linhas, subtotal, erro).

    Valida existencia do item, se e vendido na loja e se esta na janela de
    horario.
    """
    linhas = []
    subtotal = Decimal("0.00")
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
        subtotal += _dinheiro(linha["subtotal"])
    return linhas, float(subtotal), None
