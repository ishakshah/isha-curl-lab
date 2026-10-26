"""The .env lookup: this repo's folder first, then the folder above; an empty KEY= line never hides a real key."""

import os

from app.config import load_env


def test_env_lookup_order_and_empty_values(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_KEY_A", raising=False)
    monkeypatch.delenv("TEST_KEY_B", raising=False)
    repo, above = tmp_path / "repo.env", tmp_path / "above.env"
    repo.write_text("TEST_KEY_A=\nTEST_KEY_B=from-repo\n")  # A is empty, as after copying .env.example
    above.write_text("TEST_KEY_A=from-above\nTEST_KEY_B=from-above\n")
    load_env([repo, above])
    assert os.environ["TEST_KEY_A"] == "from-above"  # the empty line did not block the real key
    assert os.environ["TEST_KEY_B"] == "from-repo"   # the repo folder wins when both have a value
