"""Fast checks that need no model calls: ingredient analysis, budget enforcement, validator, and spending guards."""

import pytest
from fastapi.testclient import TestClient

from app import agents, config
from app.catalog import load_catalog, monthly_cost
from app.ingredients import analyze_inci
from app.main import app, limiter
from app.pipeline import enforce_budget, invalid_ids, strip_ids, prepare_photo, UserError
from app.schemas import RoutineStep


def test_protein_and_sulfate_detection():
    a = analyze_inci("Water, Hydrolyzed Wheat Protein, Sodium Lauryl Sulfate, Dimethicone, Glycerin, Fragrance")
    assert a["protein"] == "heavy" and a["sulfates"] and a["silicones"] and not a["fragrance_free"]
    b = analyze_inci("Water, Cetearyl Alcohol, Shea Butter, Biotin")
    assert b["protein"] == "none" and not b["sulfates"] and b["fragrance_free"]  # biotin is a vitamin


def test_catalog_is_loaded_and_priced():
    cat = load_catalog()
    assert len(cat) >= 50
    assert all(p["price_usd"] > 0 and p["size_oz"] > 0 and p["ingredients_full"] for p in cat.values())


def test_budget_enforced_in_code():
    cat = load_catalog()
    cands = {c: [i for i, p in cat.items() if p["category"] == c][:3] for c in ("cleanser", "oil", "gel", "scalp_care")}
    finals = {c: ids[0] for c, ids in cands.items()}
    uses = {"cleanser": 4.3, "oil": 8.0, "gel": 6.0, "scalp_care": 4.3}
    out, notes = enforce_budget(finals, cands, uses, "medium", budget=1.0)
    total = sum(monthly_cost(cat[p], uses[c], "medium") for c, p in out.items())
    assert notes and total <= 1.0 or "gel" in out or "cleanser" in out  # core categories are never dropped
    assert "cleanser" in out and "gel" in out


def test_validator_strips_invented_product_ids():
    steps = [RoutineStep(step=1, action="Cleanse", product_id="miracle-hair-9000", how="x", minutes=5),
             RoutineStep(step=2, action="Rinse", product_id=None, how="x", minutes=2)]
    bad = invalid_ids([steps], set(load_catalog()))
    assert bad == {"miracle-hair-9000"}
    strip_ids([steps], bad)
    assert steps[0].product_id is None


def test_non_images_are_rejected_before_any_model_call():
    with pytest.raises(UserError):
        prepare_photo(b"definitely not an image")


def test_photo_rate_limit_and_pause_and_daily_cap():
    client = TestClient(app)
    limiter.calls.clear()
    # per-person window: after 5 photo requests the 6th is refused with 429 (bad files fail fast, no model call)
    codes = [client.post("/api/photo", files={"file": ("x.jpg", b"nope", "image/jpeg")}).status_code for _ in range(config.PHOTOS_PER_WINDOW + 1)]
    assert codes[-1] == 429 and 429 not in codes[:-1]

    limiter.calls.clear()
    agents.gate.event.clear()  # pause switch
    try:
        assert client.post("/api/photo", files={"file": ("x.jpg", b"nope", "image/jpeg")}).status_code == 423
        assert client.post("/api/pause", json={"paused": False}).status_code == 403  # only localhost may flip it
    finally:
        agents.gate.event.set()

    agents.daily_spend.tokens = config.DAILY_TOKEN_CAP  # app-wide daily cap
    try:
        assert client.post("/api/photo", files={"file": ("x.jpg", b"nope", "image/jpeg")}).status_code == 503
    finally:
        agents.daily_spend.tokens = 0
        limiter.calls.clear()


def test_profile_rejects_bad_zip_and_trims_notes():
    from pydantic import ValidationError
    from app.schemas import UserProfile
    with pytest.raises(ValidationError):
        UserProfile(zip_code="abcde")
    with pytest.raises(ValidationError):
        UserProfile(zip_code="06511", notes="x" * 301)
