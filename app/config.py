"""Settings shared by every agent: the one model, credentials, and spending limits."""

import os
from pathlib import Path

from dotenv import dotenv_values
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"



def load_env(paths: list[Path]) -> None:
    """Read .env files in order; the first non-empty value for each name wins (an empty `KEY=` line, like the
    one copied from .env.example, never hides a real key in a later file)."""
    for path in paths:
        for name, value in dotenv_values(path).items():
            if value and not os.environ.get(name):
                os.environ[name] = value


# This repo's .env first, then the folder above it (where graders keep theirs).
load_env([PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"])

MODEL_NAME = "gpt-6-luna"  # the only model for every agent; no fallback

# Per-build limits, shared by every agent in one routine build (same numbers as HW5's per-ticket limits).
# Started at HW5's numbers (40 / 60 / 150,000); lowered on 2026-10-25 with the user's OK after a real build
# measured about 25,000 tokens and 20 tool calls. Tool calls raised 30 -> 45 on 2026-10-26 with the user's OK after
# a long 4C profile hit 30 in the evaluation.
REQUEST_LIMIT = 20
TOOL_CALLS_LIMIT = 45
TOTAL_TOKENS_LIMIT = 60_000
MAX_OUTPUT_TOKENS = 2_000  # per model response

# Abuse limits, modeled on HW4's per-person rate limit (sliding window) plus an app-wide daily cap.
RATE_WINDOW_SECONDS = 600
BUILDS_PER_WINDOW = 5
PHOTOS_PER_WINDOW = 5
DAILY_TOKEN_CAP = 2_000_000  # all users together; new runs are refused after this. Confirmed by the user 2026-10-25.

# gpt-6-luna list prices, USD per 1M tokens (OpenAI model page, checked 2026-10-25; prompts over 272K tokens cost more,
# which this app never reaches). Used only for cost estimates; Portkey is the real bill.
PRICE_PER_M = {"input": 0.10, "cached_input": 0.01, "output": 0.50}


def estimate_cost_usd(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """input_tokens includes cached_tokens, as the API reports them."""
    fresh = input_tokens - cached_tokens
    return (fresh * PRICE_PER_M["input"] + cached_tokens * PRICE_PER_M["cached_input"] + output_tokens * PRICE_PER_M["output"]) / 1_000_000


MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_NOTES_CHARS = 300


def build_model() -> OpenAIResponsesModel:
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Copy .env.example to .env and add your key.")
    client = AsyncOpenAI(
        api_key=key,
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": key},
    )
    # Responses API: gpt-6-luna rejects tool calls with reasoning on via /v1/chat/completions.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
