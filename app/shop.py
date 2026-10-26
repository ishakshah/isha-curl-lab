"""Product choice and cost math in plain code, with no model call.

The agents propose products; everything here is deterministic. It also powers the "fine-tune" panel on the
Products & cost page (budget slider, store, ingredient filters), which re-picks products instantly from the
verified catalog using the same rules the budget agent is held to.
"""

from collections import Counter

from app import tools
from app.catalog import cost_per_use, get_product, load_catalog, monthly_cost, public_view

# These categories are never dropped to save money (the budget agent is told the same).
CORE_CATEGORIES = {"cleanser", "cowash", "conditioner", "leave_in", "curl_cream", "gel"}
DROP_ORDER = ["scalp_care", "oil", "mousse", "clarifier", "protein_treatment", "deep_conditioner"]
# With money to spare, the most important steps get the upgrade first.
UPGRADE_ORDER = ["conditioner", "leave_in", "curl_cream", "gel", "cleanser", "cowash", "deep_conditioner",
                 "protein_treatment", "clarifier", "mousse", "oil", "scalp_care"]


def enforce_budget(
    finals: dict[str, str], candidates: dict[str, list[str]], uses: dict[str, float], hair_length: str, budget: float,
) -> tuple[dict[str, str], list[str]]:
    """Swap to cheaper candidates, then drop optional categories, until the monthly cost fits. Returns (final, notes)."""
    finals, notes = dict(finals), []

    def cost(cat: str, pid: str) -> float:
        return monthly_cost(get_product(pid), uses.get(cat, 0.0), hair_length)

    def total() -> float:
        return sum(cost(c, p) for c, p in finals.items())

    while total() > budget:
        best = None  # (saving, category, new_id)
        for cat, pid in finals.items():
            for alt in candidates.get(cat, []):
                saving = cost(cat, pid) - cost(cat, alt)
                if get_product(alt) and saving > 0.005 and (best is None or saving > best[0]):
                    best = (saving, cat, alt)
        if best:
            saving, cat, alt = best
            notes.append(f"Swapped {cat} to a cheaper option: saves ${saving:.2f}/month.")
            finals[cat] = alt
            continue
        # A deep conditioner that stands in for rinse-out conditioner is the only conditioning step, so it stays.
        only_conditioning = not ({"conditioner", "cowash"} & finals.keys())
        droppable = [c for c in DROP_ORDER if c in finals and c not in CORE_CATEGORIES and not (c == "deep_conditioner" and only_conditioning)]
        if not droppable:
            break
        gone = droppable[0]
        notes.append(f"Dropped {gone.replace('_', ' ')} to fit the budget: saves ${cost(gone, finals[gone]):.2f}/month.")
        del finals[gone]
    return finals, notes


def product_rows(finals: dict[str, str], uses: dict[str, float], hair_length: str, why: dict[str, str] | None = None) -> list[dict]:
    rows = []
    for cat, pid in finals.items():
        p = get_product(pid)
        rows.append({
            **public_view(p), "why": (why or {}).get(pid, ""), "uses_per_month": round(uses.get(cat, 0), 1),
            "cost_per_use": cost_per_use(p, hair_length), "monthly_cost": monthly_cost(p, uses.get(cat, 0), hair_length),
        })
    rows.sort(key=lambda r: tools.CATEGORY_ORDER.index(r["category"]))
    return rows


def cost_summary(rows: list[dict], budget: float, adjustments: list[dict], summary: str = "") -> dict:
    total = round(sum(r["monthly_cost"] for r in rows), 2)
    return {
        "monthly_total": total, "budget": budget, "within_budget": total <= budget,
        "upfront_total": round(sum(r["price_usd"] for r in rows), 2),
        "budget_agent_summary": summary, "adjustments": adjustments,
    }


def describe_adjustments(first: dict[str, str], finals: dict[str, str], uses: dict[str, float], hair_length: str) -> list[dict]:
    """What changed between the first-choice products and the final ones, with names and monthly savings."""
    def cost(cat: str, pid: str) -> float:
        return monthly_cost(get_product(pid), uses.get(cat, 0), hair_length)

    out = []
    for cat, was_id in first.items():
        label = cat.replace("_", " ")
        if cat not in finals:
            used = uses.get(cat, 0) >= 0.25
            out.append({
                "kind": "dropped" if used else "unused", "category": cat, "saves": cost(cat, was_id) if used else 0.0,
                "text": f"Left out {label} to stay within your budget." if used else f"Left out {label}: your schedule doesn't use it.",
            })
        elif finals[cat] != was_id:
            was, now = get_product(was_id), get_product(finals[cat])
            saves = round(cost(cat, was_id) - cost(cat, finals[cat]), 2)
            out.append({
                "kind": "swap" if saves > 0 else "upgrade", "category": cat, "saves": saves,
                "text": f"{now['brand']} {now['name']} instead of {was['brand']} {was['name']}.",
            })
    return out


def store_options() -> list[dict]:
    counts = Counter(s for p in load_catalog().values() for s in p.get("stores", []))
    return [{"store": s, "count": n} for s, n in counts.most_common()]


def plan_products(
    needs: list[dict], hair_length: str, budget: float, curl_group: str | None, porosity: str | None,
    store: str | None = None, sulfate_free: bool = False, silicone_free: bool = False, fragrance_free: bool = False,
    essentials_only: bool = False,
) -> dict:
    """Pick a product for each need so the monthly cost fits the budget. Cheaper swaps and dropped optional steps when
    money is tight; pricier options of equal fit when there is room to spare."""
    uses, rows_by_cat, unavailable = {}, {}, []
    for n in needs:
        cat = n["category"]
        if cat in rows_by_cat or (essentials_only and cat not in CORE_CATEGORIES) or n["uses_per_month"] < 0.25:
            continue
        found = tools.search_catalog(
            cat, max_protein=n["max_protein"], sulfate_free=sulfate_free, silicone_free=silicone_free,
            fragrance_free=fragrance_free, curl_group=curl_group, porosity=porosity,
            prefer_humectants=n.get("prefer_humectants"), store=store, limit=8,
        )
        uses[cat] = n["uses_per_month"]
        if found:
            rows_by_cat[cat] = found
        else:
            unavailable.append(cat)

    cands = {c: [r["id"] for r in rows] for c, rows in rows_by_cat.items()}
    fit = {r["id"]: r["fit"] for rows in rows_by_cat.values() for r in rows}
    first = {c: ids[0] for c, ids in cands.items()}
    finals, _ = enforce_budget(first, cands, uses, hair_length, budget)

    def cost(cat: str, pid: str) -> float:
        return monthly_cost(get_product(pid), uses[cat], hair_length)

    total = sum(cost(c, p) for c, p in finals.items())
    if total <= budget:  # room to spare: upgrade to pricier options that fit as well or better
        for cat in [c for c in UPGRADE_ORDER if c in finals]:
            cur, room = finals[cat], budget - total
            best = None
            for pid in cands[cat]:
                delta = cost(cat, pid) - cost(cat, cur)
                if fit[pid] >= fit[cur] and 0.005 < delta <= room and (best is None or delta > best[0]):
                    best = (delta, pid)
            if best:
                finals[cat] = best[1]
                total += best[0]

    rows = product_rows(finals, uses, hair_length)
    carries_all = None
    for r in rows:
        carries_all = set(r["stores"]) if carries_all is None else carries_all & set(r["stores"])
    return {
        "products": rows,
        "costs": cost_summary(rows, budget, describe_adjustments(first, finals, uses, hair_length)),
        "unavailable": unavailable,
        "stores_all": sorted(carries_all or []),
    }
