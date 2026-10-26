"""Run the app's agent team on 10 varied profiles and check every result with plain code.

    python scripts/run_eval.py            # about 10 runs, roughly $0.05 in total

Writes output/eval/eval_results.json. Checks per profile: catalog-only products, budget, ingredient
preferences, protein limits, time limits, and the medical flag.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from app.agents import RunContext_
from app.catalog import get_product, load_catalog
from app.catalog import protein_rank
from app.pipeline import UserError, build_routine
from app.schemas import UserProfile

PROFILES = [
    ("2B fine waves, short, quick routine", dict(zip_code="60614", curl_pattern="2B", porosity="medium", strand_width="fine", hair_length="short", style_goal="wash_and_go", wash_every_days=3, minutes_per_day=5, wash_day_minutes=40, monthly_budget_usd=20, sulfate_free=True, concerns=["frizz", "definition"])),
    ("3A, color-treated and heat-styled", dict(zip_code="30303", curl_pattern="3A", porosity="medium", hair_length="medium", color_treated=True, heat_styled=True, elasticity="snaps_quickly", style_goal="wash_and_go", wash_every_days=5, minutes_per_day=15, wash_day_minutes=75, monthly_budget_usd=40, concerns=["breakage", "dryness"])),
    ("3C high porosity, long, twist-outs", dict(zip_code="77002", curl_pattern="3C", porosity="high", hair_length="long", style_goal="twist_or_braid_out", wash_every_days=7, minutes_per_day=20, wash_day_minutes=150, monthly_budget_usd=35, concerns=["dryness", "frizz", "shrinkage"])),
    ("4A short natural / TWA, tight budget", dict(zip_code="90012", curl_pattern="4A", hair_length="short", style_goal="short_and_simple", wash_every_days=7, minutes_per_day=10, wash_day_minutes=60, monthly_budget_usd=15, concerns=["dryness"])),
    ("4B braids, flaky scalp, fragrance-free", dict(zip_code="10027", curl_pattern="4B", porosity="low", hair_length="medium", style_goal="protective_style", wash_every_days=14, minutes_per_day=10, wash_day_minutes=120, monthly_budget_usd=30, fragrance_free=True, concerns=["flaky_scalp", "dryness"])),
    ("4C long, relaxed history, generous budget", dict(zip_code="98101", curl_pattern="4C", porosity="high", hair_length="long", chemically_relaxed_or_bleached=True, elasticity="stretches_and_stays_stretched", style_goal="wash_and_go", wash_every_days=7, minutes_per_day=20, wash_day_minutes=180, monthly_budget_usd=60, concerns=["breakage", "definition"])),
    ("Locs, buildup, silicone-free", dict(zip_code="33101", curl_pattern="4B", hair_length="medium", style_goal="locs", wash_every_days=10, minutes_per_day=10, wash_day_minutes=90, monthly_budget_usd=25, silicone_free=True, concerns=["buildup"])),
    ("3B buzzed, very low budget", dict(zip_code="06511", curl_pattern="3B", hair_length="buzzed_or_very_short", style_goal="low_manipulation", wash_every_days=4, minutes_per_day=5, wash_day_minutes=30, monthly_budget_usd=10)),
    ("3B all three ingredient filters, thinning", dict(zip_code="80202", curl_pattern="3B", porosity="medium", hair_length="medium", style_goal="twist_or_braid_out", wash_every_days=7, minutes_per_day=15, wash_day_minutes=90, monthly_budget_usd=45, sulfate_free=True, silicone_free=True, fragrance_free=True, concerns=["thinning", "tangles"])),
    ("2C bleached, stretchy hair, bigger budget", dict(zip_code="94110", curl_pattern="2C", porosity="high", hair_length="medium", chemically_relaxed_or_bleached=True, elasticity="stretches_and_stays_stretched", style_goal="wash_and_go", wash_every_days=3, minutes_per_day=30, wash_day_minutes=90, monthly_budget_usd=80, concerns=["breakage", "frizz"])),
]


def check(profile: UserProfile, r: dict) -> dict:
    catalog = load_catalog()
    prods = r["products"]
    ids = {p["id"] for p in prods}
    step_ids = {s["product_id"] for k in ("wash_day_steps", "refresh_steps", "deep_condition_steps", "protein_steps", "clarify_steps") for s in r["routine"][k] if s["product_id"]}
    max_protein = {n["category"]: n["max_protein"] for n in r["needs"]}
    full = [catalog[i] for i in ids if i in catalog]
    wash_min = sum(s["minutes"] for s in r["routine"]["wash_day_steps"])
    refresh_min = sum(s["minutes"] for s in r["routine"]["refresh_steps"])
    return {
        "catalog_only": ids <= set(catalog) and step_ids <= ids,
        "within_budget": r["costs"]["within_budget"],
        "monthly_total": r["costs"]["monthly_total"],
        "prefs_ok": all(not (profile.sulfate_free and p["sulfates"]) and not (profile.silicone_free and p["silicones"]) and not (profile.fragrance_free and not p["fragrance_free"]) for p in full),
        "protein_ok": all(protein_rank(p["protein"]) <= protein_rank(max_protein.get(p["category"], "heavy")) for p in full),
        "wash_minutes": wash_min, "wash_time_ok": wash_min <= profile.wash_day_minutes,
        "refresh_minutes": refresh_min, "refresh_time_ok": refresh_min <= profile.minutes_per_day,
        "medical_flag_ok": ("thinning" not in profile.concerns) or r["hair"]["see_a_professional"],
        "weather": r["weather"] is not None,
        "products": [f'{p["brand"]} {p["name"]}' for p in prods],
    }


async def one(i: int, label: str, kw: dict, sem: asyncio.Semaphore) -> dict:
    profile = UserProfile(**kw)
    async with sem:
        ctx = RunContext_(kind="eval")
        t0 = time.time()
        try:
            r = await build_routine(profile, ctx)
            out = {"ok": True, **check(profile, r), "usage": r["usage"]["total"], "agents": r["usage"]["agents"]}
        except (UserError, Exception) as e:  # a failed run is a result too
            out = {"ok": False, "error": f"{type(e).__name__}: {e}", "usage": ctx.totals()}
        out.update(profile=label, seconds=round(time.time() - t0, 1), budget=profile.monthly_budget_usd)
        print(f"{i + 1:>2}. {label[:44]:44} {'ok ' if out['ok'] else 'FAIL'} {out.get('error', '')[:70]}", flush=True)
        return out


async def main():
    sem = asyncio.Semaphore(3)
    only = [int(a) - 1 for a in sys.argv[2:]] if len(sys.argv) > 2 and sys.argv[1] == "--only" else None  # re-run chosen profiles
    chosen = [(i, p) for i, p in enumerate(PROFILES) if only is None or i in only]
    results = await asyncio.gather(*(one(i, l, kw, sem) for i, (l, kw) in chosen))
    path = Path(__file__).resolve().parent.parent / "output" / "eval" / ("eval_results.json" if only is None else "eval_rerun.json")
    path.write_text(json.dumps(results, indent=1))
    ok = [r for r in results if r["ok"]]
    for key in ("catalog_only", "prefs_ok", "protein_ok", "wash_time_ok", "refresh_time_ok", "medical_flag_ok", "within_budget"):
        print(f"{key:18} {sum(r[key] for r in ok)}/{len(results)}")
    print("total cost $%.4f, tokens %d" % (sum(r["usage"]["cost_usd"] for r in results), sum(r["usage"]["input_tokens"] + r["usage"]["output_tokens"] for r in results)))


if __name__ == "__main__":
    asyncio.run(main())
