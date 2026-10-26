"""Tools the agents can call. Every fact an agent uses comes from one of these, not from the model's memory."""

import time
from datetime import date

import httpx

from app.catalog import cost_per_use, get_product, load_catalog, monthly_cost, protein_rank, public_view
from app.ingredients import GLOSSARY
from app.schemas import DayWeather

CATEGORY_ORDER = [
    "cleanser", "clarifier", "cowash", "conditioner", "deep_conditioner", "protein_treatment",
    "leave_in", "curl_cream", "gel", "mousse", "oil", "scalp_care",
]


# ---------- Catalog search (Products agent) ----------

def search_catalog(
    category: str,
    max_protein: str = "heavy",
    sulfate_free: bool = False,
    silicone_free: bool = False,
    fragrance_free: bool = False,
    curl_group: str | None = None,
    porosity: str | None = None,
    prefer_humectants: bool | None = None,
    max_price_usd: float | None = None,
    store: str | None = None,
    limit: int = 6,
) -> list[dict]:
    """Search the verified US catalog. Returns the best matches, cheapest first among equal fits."""
    max_rank = protein_rank(max_protein)
    scored = []
    for p in load_catalog().values():
        if p["category"] != category:
            continue
        if protein_rank(p["protein"]) > max_rank:
            continue
        if sulfate_free and p["sulfates"]:
            continue
        if silicone_free and p["silicones"]:
            continue
        if fragrance_free and not p["fragrance_free"]:
            continue
        if max_price_usd is not None and p["price_usd"] > max_price_usd:
            continue
        if store and store.lower() not in [x.lower() for x in p.get("stores", [])]:
            continue
        score = 0
        if curl_group and curl_group in p.get("marketed_for", []):
            score += 2
        if porosity == "low" and p["rich"]:
            score -= 1
        if porosity == "high" and p["rich"]:
            score += 1
        if prefer_humectants is True and p["humectant_heavy"]:
            score += 1
        if prefer_humectants is False and p["humectant_heavy"]:
            score -= 2
        if p["drying_alcohol"]:
            score -= 2
        scored.append((-score, p["price_per_oz"], p["id"], p))
    scored.sort(key=lambda t: t[:3])
    return [{**public_view(t[3]), "fit": -t[0]} for t in scored[: max(1, min(limit, 10))]]


def explain_ingredients(topics: list[str]) -> dict[str, str]:
    """Plain-language notes on ingredient families (protein, glycerin, silicones, ...)."""
    out = {}
    for t in topics[:8]:
        key = t.strip().lower()
        hit = next((k for k in GLOSSARY if k in key or key in k), None)
        out[t] = GLOSSARY[hit] if hit else "No note for this term. Do not make claims about it."
    return out


# ---------- Cost math (Budget agent) ----------

def product_cost(product_id: str, uses_per_month: float, hair_length: str) -> dict:
    p = get_product(product_id)
    if not p:
        return {"error": f"Unknown product id: {product_id}"}
    per_use = cost_per_use(p, hair_length)
    return {
        "product_id": product_id,
        "price_usd": p["price_usd"],
        "cost_per_use": per_use,
        "monthly_cost": monthly_cost(p, uses_per_month, hair_length),
        "upfront_cost": p["price_usd"],
    }


def monthly_uses(schedule: dict, wash_style: str) -> dict[str, float]:
    """How many times per month each product category gets used, from the planned schedule."""
    washes = schedule["washes_per_month"]
    refreshes = schedule["refreshes_per_month"]
    styling = washes + 0.5 * refreshes
    return {
        "cleanser": washes if wash_style != "mostly_cowash" else washes * 0.5,
        "clarifier": 1.0,
        "cowash": washes if wash_style == "mostly_cowash" else 0.0,
        "conditioner": max(washes - schedule["deep_conditions_per_month"], 0.0),
        "deep_conditioner": schedule["deep_conditions_per_month"],
        "protein_treatment": schedule["protein_treatments_per_month"],
        "leave_in": styling,
        "curl_cream": styling,
        "gel": styling,
        "mousse": styling,
        "oil": styling,
        "scalp_care": washes,
    }


# ---------- Weather (Weather agent) ----------

_forecast_cache: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 1800


def climate_band(dew_point_f: float) -> str:
    """Dew point is a better guide to frizz than humidity: under 30 dry, 30-49 comfortable, 50-59 muggy, 60+ very humid."""
    if dew_point_f < 30:
        return "dry"
    if dew_point_f < 50:
        return "comfortable"
    if dew_point_f < 60:
        return "muggy"
    return "very_humid"


async def fetch_forecast(zip_code: str) -> dict:
    """Seven-day forecast for a US ZIP code from two free services that need no key."""
    cached = _forecast_cache.get(zip_code)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    async with httpx.AsyncClient(timeout=15) as client:
        z = await client.get(f"https://api.zippopotam.us/us/{zip_code}")
        if z.status_code != 200:
            raise ValueError(f"ZIP code {zip_code} was not found.")
        place = z.json()["places"][0]
        r = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"], "longitude": place["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,dew_point_2m_mean,relative_humidity_2m_mean,"
                         "uv_index_max,wind_speed_10m_max,precipitation_probability_max",
                "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "timezone": "auto", "forecast_days": 7,
            },
        )
        r.raise_for_status()
    d = r.json()["daily"]
    days = []
    for i, day in enumerate(d["time"]):
        dew = d["dew_point_2m_mean"][i]
        days.append(DayWeather(
            date=day, temp_hi_f=round(d["temperature_2m_max"][i]), temp_lo_f=round(d["temperature_2m_min"][i]),
            dew_point_f=round(dew), humidity_pct=round(d["relative_humidity_2m_mean"][i]),
            uv_index=round(d["uv_index_max"][i], 1), wind_mph=round(d["wind_speed_10m_max"][i]),
            rain_chance_pct=round(d["precipitation_probability_max"][i] or 0), climate=climate_band(dew),
        ).model_dump())
    result = {"place": f"{place['place name']}, {place['state abbreviation']}", "days": days}
    _forecast_cache[zip_code] = (time.time(), result)
    return result


def today_iso() -> str:
    return date.today().isoformat()
