"""Materiais que a busca conhece e como eles aparecem no OpenStreetMap."""

# chave: (rotulo, sufixos da etiqueta `recycling:*` do OpenStreetMap)
MATERIAIS: dict[str, tuple[str, tuple[str, ...]]] = {
    "papel": ("Papel e papelão", ("paper", "cardboard", "newspaper", "magazines", "paper_packaging", "cartons", "books")),
    "plastico": ("Plástico", ("plastic", "plastic_bottles", "plastic_packaging", "plastic_bags")),
    "vidro": ("Vidro", ("glass", "glass_bottles")),
    "metal": ("Metal e sucata", ("metal", "cans", "scrap_metal", "aluminium")),
    "eletronicos": ("Eletrônicos e eletrodomésticos", ("electrical_items", "small_appliances", "computers", "mobile_phones", "printer_cartridges", "white_goods")),
    "pilhas": ("Pilhas e baterias", ("batteries", "car_batteries")),
    "oleo": ("Óleo de cozinha", ("cooking_oil",)),
    "entulho": ("Entulho", ("rubble",)),
    "pneus": ("Pneus", ("tyres",)),
    "moveis": ("Móveis", ("furniture",)),
    "galhos": ("Galhos e podas", ("green_waste", "garden_waste")),
    "agrotoxicos": ("Embalagens de agrotóxicos", ()),
}


def materiais_das_etiquetas(etiquetas: dict[str, str]) -> list[str]:
    """Le as etiquetas `recycling:* = yes` e devolve as chaves de material."""
    return [
        chave
        for chave, (_, sufixos) in MATERIAIS.items()
        if any(etiquetas.get(f"recycling:{sufixo}") == "yes" for sufixo in sufixos)
    ]


def para_saida(chaves: list[str]) -> list[dict[str, str]]:
    return [{"chave": chave, "rotulo": MATERIAIS[chave][0]} for chave in chaves]
