"""Dados fixos do delivery: lojas, bordas, categorias e indice do cardapio.

O cardapio em si (≈110 itens) fica em cardapio_itens.py, gerado a parte,
pra manter este arquivo enxuto e legivel.
"""

from cardapio_itens import ITENS

# Salgados vendidos por peso: preco por kg, e a quantidade no pedido e em gramas.
SALGADOS = [
    {"id": "sg01", "categoria": "salgados", "tipo": "peso", "nome": "Mini Coxinha de Frango",
     "descricao": "Massa crocante recheada com frango desfiado temperado", "lojas": ["A", "B"],
     "preco_por_kg": 59.90, "minimo_g": 250},
    {"id": "sg02", "categoria": "salgados", "tipo": "peso", "nome": "Mini Kibe",
     "descricao": "Bolinho de trigo com carne moida e temperos arabes", "lojas": ["A", "B"],
     "preco_por_kg": 54.90, "minimo_g": 250},
    {"id": "sg03", "categoria": "salgados", "tipo": "peso", "nome": "Mini Empada de Frango",
     "descricao": "Massa amanteigada com recheio cremoso de frango", "lojas": ["A", "B"],
     "preco_por_kg": 62.90, "minimo_g": 250},
    {"id": "sg04", "categoria": "salgados", "tipo": "peso", "nome": "Bolinha de Queijo",
     "descricao": "Bolinha empanada e recheada de queijo derretido", "lojas": ["A", "B"],
     "preco_por_kg": 57.90, "minimo_g": 250},
    {"id": "sg05", "categoria": "salgados", "tipo": "peso", "nome": "Mini Esfiha de Carne",
     "descricao": "Massa macia aberta com carne temperada", "lojas": ["A", "B"],
     "preco_por_kg": 56.90, "minimo_g": 250},
    {"id": "sg06", "categoria": "salgados", "tipo": "peso", "nome": "Mini Enroladinho de Salsicha",
     "descricao": "Massa folhada envolvendo salsicha", "lojas": ["A", "B"],
     "preco_por_kg": 52.90, "minimo_g": 250},
    {"id": "sg07", "categoria": "salgados", "tipo": "peso", "nome": "Risole de Presunto e Queijo",
     "descricao": "Massa empanada recheada de presunto e queijo", "lojas": ["A", "B"],
     "preco_por_kg": 58.90, "minimo_g": 250},
    {"id": "sg08", "categoria": "salgados", "tipo": "peso", "nome": "Mini Pastel de Queijo",
     "descricao": "Pastelzinho frito e crocante recheado de queijo", "lojas": ["A", "B"],
     "preco_por_kg": 55.90, "minimo_g": 250},
]

CARDAPIO = ITENS + SALGADOS

# Bordas de pizza e o adicional de cada uma (R$).
BORDAS = {
    "sem": 0.0,
    "catupiry": 8.0,
    "cheddar": 8.0,
    "chocolate": 10.0,
}

# Categorias na ordem em que devem ser apresentadas (chave -> rotulo).
CATEGORIAS = {
    "pizzas": "Pizzas",
    "hamburgueres": "Hamburgueres",
    "combos": "Combos",
    "porcoes": "Porcoes",
    "salgados": "Salgados (por kg)",
    "massas": "Massas",
    "japonesa": "Japonesa",
    "saladas": "Saladas",
    "cafe_da_manha": "Cafe da manha",
    "bebidas": "Bebidas",
    "sobremesas": "Sobremesas",
}

# As 2 unidades da Parla Deli. horarios: {dia_da_semana (0=segunda .. 6=domingo):
# [(abre, fecha), ...]}. As duas sao iguais: mesmo cardapio, todos os dias 8h-22h.
# (Pizza tem janela propria 16:30-22:00, definida por item no cardapio.)
LOJAS = {
    "A": {
        "id": "A",
        "nome": "Aflitos",
        "endereco": "Rua do Futuro, 255 - Aflitos, Recife/PE",
        "cep": "52050225",
        "horario_texto": "Todos os dias, das 8h as 22h",
        "horarios": {
            0: [("08:00", "22:00")],
            1: [("08:00", "22:00")],
            2: [("08:00", "22:00")],
            3: [("08:00", "22:00")],
            4: [("08:00", "22:00")],
            5: [("08:00", "22:00")],
            6: [("08:00", "22:00")],
        },
        "cidade": "Recife",
        "uf": "PE",
        "frete_base": 7.9,
        "frete_gratis_acima": 80.0,
    },
    "B": {
        "id": "B",
        "nome": "Boa Viagem",
        "endereco": "Av. Boa Viagem, 3000 - Boa Viagem, Recife/PE",
        "cep": "51020000",
        "horario_texto": "Todos os dias, das 8h as 22h",
        "horarios": {
            0: [("08:00", "22:00")],
            1: [("08:00", "22:00")],
            2: [("08:00", "22:00")],
            3: [("08:00", "22:00")],
            4: [("08:00", "22:00")],
            5: [("08:00", "22:00")],
            6: [("08:00", "22:00")],
        },
        "cidade": "Recife",
        "uf": "PE",
        "frete_base": 7.9,
        "frete_gratis_acima": 80.0,
    },
}

# Indice id -> item, montado uma vez no carregamento do modulo.
_INDICE = {item["id"]: item for item in CARDAPIO}


def get_item(item_id):
    """Retorna o item do cardapio pelo id, ou None."""
    return _INDICE.get(item_id)
