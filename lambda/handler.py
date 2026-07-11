import json
import urllib.request
import uuid

CARDAPIO = [
    {"id": "x1", "nome": "X-Burger", "descricao": "Pao, hamburguer 150g, queijo", "preco": 22.90},
    {"id": "x2", "nome": "X-Salada", "descricao": "Pao, hamburguer 150g, queijo, alface, tomate", "preco": 25.90},
    {"id": "x3", "nome": "X-Bacon", "descricao": "Pao, hamburguer 150g, queijo, bacon", "preco": 28.90},
    {"id": "b1", "nome": "Refrigerante lata", "descricao": "350ml", "preco": 7.00},
    {"id": "b2", "nome": "Suco natural", "descricao": "Laranja 400ml", "preco": 10.00},
    {"id": "s1", "nome": "Batata frita", "descricao": "Porcao 200g", "preco": 15.00},
]

TAXA_ENTREGA = 8.00


def consultar_cardapio():
    return {"cardapio": CARDAPIO, "taxa_entrega": TAXA_ENTREGA}


def validar_cep(cep):
    digitos = "".join(c for c in str(cep) if c.isdigit())
    if len(digitos) != 8:
        return {"valido": False, "erro": "CEP deve conter 8 digitos"}
    try:
        req = urllib.request.Request(
            f"https://viacep.com.br/ws/{digitos}/json/",
            headers={"User-Agent": "agente-pedidos-estudo"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {"valido": False, "erro": "Falha ao consultar o CEP, tente novamente"}
    if data.get("erro"):
        return {"valido": False, "erro": "CEP nao encontrado"}
    return {
        "valido": True,
        "endereco": {
            "logradouro": data.get("logradouro"),
            "bairro": data.get("bairro"),
            "cidade": data.get("localidade"),
            "uf": data.get("uf"),
            "cep": digitos,
        },
    }


def criar_pedido(params):
    try:
        itens = json.loads(params.get("itens", "[]"))
    except json.JSONDecodeError:
        return {"sucesso": False, "erro": "Formato de itens invalido"}
    if not itens:
        return {"sucesso": False, "erro": "Pedido sem itens"}

    catalogo = {item["id"]: item for item in CARDAPIO}
    resumo = []
    subtotal = 0.0

    for item in itens:
        produto = catalogo.get(item.get("id"))
        qtd = int(item.get("qtd", 0))
        if not produto or qtd < 1:
            return {"sucesso": False, "erro": f"Item invalido: {item}"}
        subtotal += produto["preco"] * qtd
        resumo.append({"nome": produto["nome"], "qtd": qtd, "preco_unitario": produto["preco"]})

    return {
        "sucesso": True,
        "pedido_id": f"PED-{uuid.uuid4().hex[:8].upper()}",
        "cliente": params.get("nome_cliente"),
        "cep_entrega": params.get("cep"),
        "itens": resumo,
        "subtotal": round(subtotal, 2),
        "taxa_entrega": TAXA_ENTREGA,
        "total": round(subtotal + TAXA_ENTREGA, 2),
    }


def lambda_handler(event, context):
    function = event.get("function", "")
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    if function == "consultar_cardapio":
        result = consultar_cardapio()
    elif function == "validar_cep":
        result = validar_cep(params.get("cep", ""))
    elif function == "criar_pedido":
        result = criar_pedido(params)
    else:
        result = {"erro": f"Funcao desconhecida: {function}"}

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
