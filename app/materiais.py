"""Materiais que a busca conhece e como eles aparecem no OpenStreetMap."""

MATERIAIS = {
    "papel": "Papel e papelão",
    "plastico": "Plástico",
    "vidro": "Vidro",
    "metal": "Metal e sucata",
    "eletronicos": "Eletrônicos e eletrodomésticos",
    "pilhas": "Pilhas e baterias",
    "oleo": "Óleo de cozinha",
    "entulho": "Entulho",
    "pneus": "Pneus",
    "moveis": "Móveis",
    "galhos": "Galhos e podas",
    "agrotoxicos": "Embalagens de agrotóxicos",
}

# Etiqueta `recycling:*` do OpenStreetMap -> material.
ETIQUETAS_OSM = {
    "paper": "papel",
    "cardboard": "papel",
    "newspaper": "papel",
    "magazines": "papel",
    "paper_packaging": "papel",
    "cartons": "papel",
    "books": "papel",
    "plastic": "plastico",
    "plastic_bottles": "plastico",
    "plastic_packaging": "plastico",
    "plastic_bags": "plastico",
    "glass": "vidro",
    "glass_bottles": "vidro",
    "metal": "metal",
    "cans": "metal",
    "scrap_metal": "metal",
    "aluminium": "metal",
    "electrical_items": "eletronicos",
    "small_appliances": "eletronicos",
    "computers": "eletronicos",
    "mobile_phones": "eletronicos",
    "printer_cartridges": "eletronicos",
    "white_goods": "eletronicos",
    "batteries": "pilhas",
    "car_batteries": "pilhas",
    "cooking_oil": "oleo",
    "rubble": "entulho",
    "tyres": "pneus",
    "furniture": "moveis",
    "green_waste": "galhos",
    "garden_waste": "galhos",
}


def materiais_das_etiquetas(etiquetas: dict[str, str]) -> list[str]:
    """Le as etiquetas `recycling:* = yes` e devolve as chaves de material."""
    aceitos = {
        material
        for etiqueta, material in ETIQUETAS_OSM.items()
        if etiquetas.get(f"recycling:{etiqueta}") == "yes"
    }
    return [chave for chave in MATERIAIS if chave in aceitos]


def para_saida(chaves: list[str]) -> list[dict[str, str]]:
    return [{"chave": chave, "rotulo": MATERIAIS[chave]} for chave in chaves]
