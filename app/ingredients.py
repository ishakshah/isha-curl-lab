"""Ingredient (INCI) analysis in plain code.

The catalog stores each product's full ingredient list exactly as the brand prints it. Everything the
agents know about protein, sulfates, silicones and so on is computed here from that list, so a model
can never "remember" an ingredient wrongly.
"""

import re

PROTEIN_RE = re.compile(
    r"hydrolyzed (?!jojoba|candelilla|sweet almond|hyaluronic|algin|sodium|glycosaminoglycans?)[\w\s/-]*?"
    r"(protein|keratin|collagen|elastin|silk|casein)"
    r"|\bkeratin\b|\bcollagen\b|\belastin\b|amino acids?\b|\bsilk\b|\bprotein\b|\bcasein\b|\bbiotin\b(?!\w)",
    re.I,
)
# Biotin is a vitamin, not a protein; it is matched above only so we can drop it again below.
HUMECTANT_RE = re.compile(r"glycerin|glycerol|honey|\bmel\b|agave|sorbitol|propylene glycol|butylene glycol|sodium pca|hyaluronic|urea|sodium lactate", re.I)
SILICONE_RE = re.compile(r"\b[\w-]*(cone|conol|siloxane|silsesquioxane)\b", re.I)
SULFATE_RE = re.compile(r"(sodium|ammonium|potassium|magnesium|tea|mea)[\s-]*(lauryl|laureth(-\d+)?|myreth|coco)[\s-]*sulfate|lauryl sulfate|laureth sulfate", re.I)
DRYING_ALCOHOL_RE = re.compile(r"alcohol denat|sd alcohol|isopropyl alcohol|^alcohol$|ethanol", re.I)
FRAGRANCE_RE = re.compile(r"fragrance|parfum", re.I)
RICH_RE = re.compile(r"shea|butyrospermum|cocoa|theobroma|mango seed|murumuru|castor|ricinus|petrolatum|mineral oil|paraffin|coconut oil|cocos nucifera oil|avocado|olive", re.I)
OCCLUSIVE_RE = re.compile(r"petrolatum|mineral oil|paraffinum liquidum|paraffin\b|microcrystalline wax|beeswax|cera alba", re.I)

PROTEIN_LEVELS = ["none", "light", "moderate", "heavy"]


def split_inci(inci: str) -> list[str]:
    """Split an ingredient list into names in label order, dropping 'may contain' tails."""
    text = re.split(r"\b(may contain|\+/-|\(may contain)", inci, flags=re.I)[0]
    text = re.sub(r"\([^)]*\)", lambda m: "" if len(m.group(0)) > 40 else m.group(0), text)
    return [part.strip(" .*†") for part in text.split(",") if part.strip(" .*†")]


def _positions(names: list[str], regex: re.Pattern) -> list[int]:
    return [i for i, n in enumerate(names) if regex.search(n)]


def analyze_inci(inci: str, category: str = "") -> dict:
    names = split_inci(inci)
    protein_idx = [i for i in _positions(names, PROTEIN_RE) if "biotin" not in names[i].lower()]
    if not protein_idx:
        protein = "none"
    elif protein_idx[0] < 5 or len(protein_idx) >= 4:
        protein = "heavy"
    elif protein_idx[0] < 10 or len(protein_idx) >= 2:
        protein = "moderate"
    else:
        protein = "light"
    if category == "protein_treatment" and PROTEIN_LEVELS.index(protein) < 2:
        protein = "moderate"  # sold as a protein treatment: never treat it as protein-free

    humectant_idx = _positions(names, HUMECTANT_RE)
    top8 = names[:8]
    return {
        "protein": protein,
        "sulfates": bool(_positions(names, SULFATE_RE)),
        "silicones": bool(_positions(names, SILICONE_RE)),
        "fragrance_free": not _positions(names, FRAGRANCE_RE),
        "drying_alcohol": any(DRYING_ALCOHOL_RE.search(n) for n in names[:10]),
        "humectant_heavy": any(HUMECTANT_RE.search(n) for n in top8) and len(humectant_idx) >= 1,
        "rich": sum(1 for n in top8 if RICH_RE.search(n)) >= 1,
        "occlusive": bool(_positions(names, OCCLUSIVE_RE)),
        "ingredient_count": len(names),
    }


# Short glossary for the hair-science agent's lookup tool.
GLOSSARY = {
    "protein": "Hydrolyzed proteins, keratin, collagen, silk and amino acids temporarily fill gaps in the strand. Too much leaves hair stiff, brittle or straw-like; too little can leave it stretchy and mushy.",
    "glycerin": "A humectant that pulls water to the hair. Helps in moderate humidity, but in very dry air it can pull water out of the hair, and in very humid air it can cause frizz and swelling.",
    "humectants": "Glycerin, honey, agave, sorbitol and propylene glycol draw in water. Best when dew point is roughly 30-50 F.",
    "silicones": "Ingredients ending in -cone or -conol coat the strand for slip and shine. They can build up on low porosity hair and need a stronger cleanser to remove.",
    "sulfates": "Strong cleansers (sodium lauryl or laureth sulfate). Effective on buildup but can dry out coily hair if used often.",
    "oils and butters": "Shea, cocoa, castor and coconut seal in moisture. Heavy ones can sit on low porosity hair.",
    "occlusives": "Petrolatum, mineral oil and waxes seal the surface and can block water from getting in.",
    "drying alcohols": "Alcohol denat and isopropyl alcohol can dry hair. Fatty alcohols like cetyl or cetearyl alcohol are conditioning, not drying.",
    "fragrance": "Added scent can irritate sensitive scalps. Essential oils are fragrance for sensitivity purposes.",
    "low porosity": "Cuticle lies flat: slow to absorb water and products. Prefers lightweight products, warmth during deep conditioning, and regular clarifying.",
    "high porosity": "Cuticle lifts or has gaps: absorbs water quickly but loses it quickly. Prefers richer creams, sealing oils and layering (leave-in, cream, gel).",
}
