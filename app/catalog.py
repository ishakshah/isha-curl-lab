"""The verified US product catalog (data/products.json) plus per-product flags computed from ingredients."""

import json
from functools import lru_cache

from app.config import DATA_DIR
from app.ingredients import PROTEIN_LEVELS, analyze_inci

# Typical amount used per application, in fluid ounces, for medium-length hair.
OZ_PER_USE = {
    "cleanser": 0.75, "clarifier": 0.75, "cowash": 1.5, "conditioner": 1.5, "deep_conditioner": 2.0,
    "protein_treatment": 2.0, "leave_in": 1.0, "curl_cream": 1.0, "gel": 1.25, "mousse": 1.0,
    "oil": 0.25, "scalp_care": 0.25,
}
LENGTH_MULTIPLIER = {"buzzed_or_very_short": 0.4, "short": 0.6, "medium": 1.0, "long": 1.5}


@lru_cache
def load_catalog() -> dict[str, dict]:
    products = json.loads((DATA_DIR / "products.json").read_text())
    catalog = {}
    for p in products:
        flags = analyze_inci(p["ingredients_full"], p["category"])
        p = {**p, **flags}
        p["price_per_oz"] = round(p["price_usd"] / p["size_oz"], 2)
        catalog[p["id"]] = p
    return catalog


def get_product(product_id: str) -> dict | None:
    return load_catalog().get(product_id)


def cost_per_use(product: dict, hair_length: str) -> float:
    oz = OZ_PER_USE[product["category"]] * LENGTH_MULTIPLIER[hair_length]
    return round(oz * product["price_per_oz"], 2)


def monthly_cost(product: dict, uses_per_month: float, hair_length: str) -> float:
    return round(cost_per_use(product, hair_length) * uses_per_month, 2)


def public_view(p: dict) -> dict:
    """What the UI and the agents see for a product (no long ingredient list for agents)."""
    return {
        "id": p["id"], "brand": p["brand"], "name": p["name"], "category": p["category"],
        "price_usd": p["price_usd"], "size_oz": p["size_oz"], "price_per_oz": p["price_per_oz"],
        "stores": p.get("stores", []), "protein": p["protein"], "sulfates": p["sulfates"],
        "silicones": p["silicones"], "fragrance_free": p["fragrance_free"],
        "humectant_heavy": p["humectant_heavy"], "rich": p["rich"], "drying_alcohol": p["drying_alcohol"],
        "marketed_for": p.get("marketed_for", []), "price_checked": p.get("price_checked"),
        "url": p.get("url"),
    }


def protein_rank(level: str) -> int:
    return PROTEIN_LEVELS.index(level)
