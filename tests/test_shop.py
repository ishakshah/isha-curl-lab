"""The fine-tune panel's product picker: budget, store and ingredient filters (no model calls)."""

from fastapi.testclient import TestClient

from app.main import app, limiter
from app.shop import plan_products

NEEDS = [{"category": c, "max_protein": "light", "prefer_humectants": None, "uses_per_month": u}
         for c, u in [("cleanser", 4.3), ("deep_conditioner", 4.3), ("leave_in", 5.0), ("curl_cream", 5.0), ("gel", 5.0), ("oil", 5.0), ("scalp_care", 4.3), ("clarifier", 1.0)]]


def plan(budget, **kw):
    return plan_products(NEEDS, "medium", budget, "curly", "medium", **kw)


def test_low_budget_swaps_and_drops_optional_steps_but_keeps_core():
    out = plan(10)
    cats = {p["category"] for p in out["products"]}
    assert {"cleanser", "leave_in"} <= cats or {"cleanser", "curl_cream"} <= cats
    assert "deep_conditioner" in cats  # the only conditioning step is never dropped
    assert {a["kind"] for a in out["costs"]["adjustments"]} & {"dropped", "swap"}


def test_more_budget_never_costs_less_and_stays_within_it():
    totals = [plan(b)["costs"]["monthly_total"] for b in (20, 60, 120)]
    assert totals == sorted(totals)
    assert all(plan(b)["costs"]["within_budget"] for b in (60, 120))


def test_single_store_filter_only_returns_that_stores_products():
    out = plan(60, store="Target")
    assert out["products"] and all("Target" in p["stores"] for p in out["products"])
    assert out["stores_all"] == ["Target"]


def test_ingredient_filters_are_respected():
    out = plan(60, sulfate_free=True, silicone_free=True, fragrance_free=True)
    assert all(not p["sulfates"] and not p["silicones"] and p["fragrance_free"] for p in out["products"])


def test_unavailable_categories_are_reported_not_invented():
    out = plan(60, store="Sephora", fragrance_free=True, silicone_free=True)
    assert out["unavailable"]  # Sephora carries only 2 products in the catalog
    assert all("Sephora" in p["stores"] for p in out["products"])


def test_essentials_only():
    cats = {p["category"] for p in plan(60, essentials_only=True)["products"]}
    assert cats <= {"cleanser", "cowash", "conditioner", "leave_in", "curl_cream", "gel"}


def test_reprice_endpoint_validates_input():
    limiter.calls.clear()
    c = TestClient(app)
    bad = c.post("/api/reprice", json={"needs": NEEDS, "hair_length": "medium", "monthly_budget_usd": 9999})
    assert bad.status_code == 422
    ok = c.post("/api/reprice", json={"needs": NEEDS, "hair_length": "medium", "monthly_budget_usd": 50, "store": "Target"})
    assert ok.status_code == 200 and ok.json()["products"]
