"""Dados fixos do delivery: lojas, bordas, categorias e indice do cardapio.

O cardapio em si (≈110 itens) fica em cardapio_itens.py, gerado a parte,
pra manter este arquivo enxuto e legivel.
"""

from cardapio_itens import ITENS as CARDAPIO

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
    "massas": "Massas",
    "japonesa": "Japonesa",
    "saladas": "Saladas",
    "cafe_da_manha": "Cafe da manha",
    "bebidas": "Bebidas",
    "sobremesas": "Sobremesas",
}

# As 2 lojas. horarios: {dia_da_semana (0=segunda .. 6=domingo): [(abre, fecha), ...]}.
LOJAS = {
    "A": {
        "id": "A",
        "nome": "Pizzaria Central",
        "endereco": "Av. Paulista, 1000 - Bela Vista, Sao Paulo/SP",
        "cep": "01310100",
        "horario_texto": "Terca a domingo, das 18h as 24h (segunda fechada)",
        "horarios": {
            0: [],
            1: [("18:00", "23:59")],
            2: [("18:00", "23:59")],
            3: [("18:00", "23:59")],
            4: [("18:00", "23:59")],
            5: [("18:00", "23:59")],
            6: [("18:00", "23:59")],
        },
        "frete_base": 6.0,
        "frete_gratis_acima": 90.0,
    },
    "B": {
        "id": "B",
        "nome": "Burger Jardins",
        "endereco": "Av. Brigadeiro Faria Lima, 2000 - Jardim Paulistano, Sao Paulo/SP",
        "cep": "04538133",
        "horario_texto": "Segunda a sabado, das 7h as 15h e das 18h as 23h (domingo fechado)",
        "horarios": {
            0: [("07:00", "15:00"), ("18:00", "23:00")],
            1: [("07:00", "15:00"), ("18:00", "23:00")],
            2: [("07:00", "15:00"), ("18:00", "23:00")],
            3: [("07:00", "15:00"), ("18:00", "23:00")],
            4: [("07:00", "15:00"), ("18:00", "23:00")],
            5: [("07:00", "15:00"), ("18:00", "23:00")],
            6: [],
        },
        "frete_base": 8.0,
        "frete_gratis_acima": 70.0,
    },
}

# Indice id -> item, montado uma vez no carregamento do modulo.
_INDICE = {item["id"]: item for item in CARDAPIO}


def get_item(item_id):
    """Retorna o item do cardapio pelo id, ou None."""
    return _INDICE.get(item_id)
