"""Same 10 profiles, asked the way a person would ask a plain chatbot: one prompt, no tools, no catalog, no forecast.

    python scripts/compare_plain_llm.py

This uses gpt-6-luna itself (the only model allowed on the course key) as a stand-in for "just asking a chatbot".
Each product it names is looked up in our verified catalog: matched products are checked for price accuracy and
ingredient preferences; unmatched ones are reported as "unverified" (they might be real, we just can't confirm them).
Writes output/eval/plain_llm_comparison.json.
"""

import asyncio
import difflib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic import BaseModel
from pydantic_ai import Agent

from app import config
from app.catalog import load_catalog
from app.config import build_model, estimate_cost_usd
from scripts.run_eval import PROFILES  # noqa: E402  (same profiles as the app evaluation)
from app.schemas import UserProfile

STYLE = {"wash_and_go": "wash-and-go", "twist_or_braid_out": "twist-outs and braid-outs", "protective_style": "protective styles like braids",
         "locs": "locs", "short_and_simple": "a short, simple cut", "low_manipulation": "low manipulation"}


def ask(p: UserProfile) -> str:
    prefs = [n for n, on in (("sulfate-free", p.sulfate_free), ("silicone-free", p.silicone_free), ("fragrance-free", p.fragrance_free)) if on]
    return (
        f"I have {p.curl_pattern} textured hair ({p.hair_length.replace('_', ' ')} length"
        f"{', ' + p.porosity + ' porosity' if p.porosity else ''}). I like {STYLE[p.style_goal]}. I wash every {p.wash_every_days} days, have "
        f"{p.minutes_per_day} minutes on a normal day and {p.wash_day_minutes} on wash day, live in ZIP {p.zip_code}, and my budget is "
        f"${p.monthly_budget_usd} a month for hair products."
        + (f" My concerns: {', '.join(c.replace('_', ' ') for c in p.concerns)}." if p.concerns else "")
        + (f" I only want {', '.join(prefs)} products." if prefs else "")
        + " Build me a curly hair routine with specific products I can buy in the US, their prices, and my total monthly cost."
    )


class Named(BaseModel):
    brand: str
    product: str
    stated_price_usd: float | None = None


class Extract(BaseModel):
    products: list[Named]
    stated_monthly_total_usd: float | None = None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("&", " and ")).strip()


def match(n: Named) -> dict | None:
    target = norm(f"{n.brand} {n.product}")
    best, score = None, 0.0
    for p in load_catalog().values():
        s = difflib.SequenceMatcher(None, target, norm(f"{p['brand']} {p['name']}")).ratio()
        if s > score:
            best, score = p, s
    return best if score >= 0.72 else None


async def one(i: int, label: str, kw: dict, sem: asyncio.Semaphore) -> dict:
    p = UserProfile(**kw)
    async with sem:
        t0 = time.time()
        chat = Agent(build_model(), model_settings={"max_tokens": 6000})
        extractor = Agent(build_model(), output_type=Extract, model_settings={"max_tokens": 3000},
                          instructions="List every specific hair product named in the answer with the price it states (null if none), and the monthly total it states (null if none).")
        a = await chat.run(ask(p))
        e = await extractor.run(a.output)
        ua, ue = a.usage, e.usage
        matched = []
        for n in e.output.products:
            m = match(n)
            matched.append({"named": f"{n.brand} {n.product}", "stated_price": n.stated_price_usd, "in_catalog": bool(m), "catalog_price": m["price_usd"] if m else None,
                            "price_ok": bool(m and n.stated_price_usd is not None and abs(n.stated_price_usd - m["price_usd"]) <= 1.5),
                            "pref_violation": bool(m and ((p.sulfate_free and m["sulfates"]) or (p.silicone_free and m["silicones"]) or (p.fragrance_free and not m["fragrance_free"])))})
        total = e.output.stated_monthly_total_usd
        out = {
            "profile": label, "n_products": len(matched), "in_catalog": sum(m["in_catalog"] for m in matched),
            "price_checked": sum(1 for m in matched if m["in_catalog"] and m["stated_price"] is not None),
            "price_ok": sum(m["price_ok"] for m in matched), "pref_violations": sum(m["pref_violation"] for m in matched),
            "stated_total": total, "budget": p.monthly_budget_usd, "claims_within_budget": (total is not None and total <= p.monthly_budget_usd),
            "used_forecast": False, "answer_words": len(a.output.split()), "products": matched,
            "usage": {"input_tokens": ua.input_tokens + ue.input_tokens, "cached_tokens": ua.cache_read_tokens + ue.cache_read_tokens,
                      "output_tokens": ua.output_tokens + ue.output_tokens,
                      "cost_usd": round(estimate_cost_usd(ua.input_tokens + ue.input_tokens, ua.cache_read_tokens + ue.cache_read_tokens, ua.output_tokens + ue.output_tokens), 6)},
            "seconds": round(time.time() - t0, 1), "answer": a.output,
        }
        print(f"{i + 1:>2}. {label[:42]:42} named {out['n_products']:>2}, in catalog {out['in_catalog']:>2}, stated total {total}", flush=True)
        return out


async def main():
    sem = asyncio.Semaphore(3)
    results = await asyncio.gather(*(one(i, l, kw, sem) for i, (l, kw) in enumerate(PROFILES)))
    (Path(__file__).resolve().parent.parent / "output" / "eval" / "plain_llm_comparison.json").write_text(json.dumps(results, indent=1))
    n = sum(r["n_products"] for r in results)
    print(f"products named {n}; verified in catalog {sum(r['in_catalog'] for r in results)}; price within $1.50 of catalog "
          f"{sum(r['price_ok'] for r in results)}/{sum(r['price_checked'] for r in results)}; preference violations {sum(r['pref_violations'] for r in results)}")
    print("cost $%.4f" % sum(r["usage"]["cost_usd"] for r in results))


if __name__ == "__main__":
    asyncio.run(main())
