"""Haircut suggestion: salon search links are plain code, and the route validates input (no model calls)."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app, limiter
from app.pipeline import salon_links


def test_links_follow_the_texture_and_use_the_zip():
    coily = salon_links("60614", "4B", "wash_and_go")
    curly = salon_links("06511", "3A", "wash_and_go")
    assert "natural hair salon" in coily[0]["url"].replace("+", " ") and "60614" in coily[0]["url"]
    assert "curly hair specialist" in curly[0]["url"].replace("+", " ") and "06511" in curly[0]["url"]
    assert "loctician" in salon_links("10027", "4B", "locs")[0]["url"]
    assert "barber" in salon_links("10027", "4A", "short_and_simple")[0]["url"]
    for link in coily + curly:
        host = urlparse(link["url"]).netloc
        assert host in ("www.google.com", "www.yelp.com")  # search links only: we never invent a salon


def test_haircut_route_validates_input():
    limiter.calls.clear()
    c = TestClient(app)
    assert c.post("/api/haircut", json={"profile": {"zip_code": "nope"}}).status_code == 422
    assert c.post("/api/haircut", json={"profile": {"zip_code": "06511"}, "prefs": {"maintenance": "extreme"}}).status_code == 422
