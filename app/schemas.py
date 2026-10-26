"""Data shapes shared by the API and the agents (structured outputs)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config import MAX_NOTES_CHARS

Level = Literal["low", "medium", "high"]
CurlPattern = Literal["2A", "2B", "2C", "3A", "3B", "3C", "4A", "4B", "4C"]
ProteinLevel = Literal["none", "light", "moderate", "heavy"]
Category = Literal[
    "cleanser", "clarifier", "cowash", "conditioner", "deep_conditioner",
    "protein_treatment", "leave_in", "curl_cream", "gel", "mousse", "oil", "scalp_care",
]

CONCERNS = ["dryness", "frizz", "breakage", "shrinkage", "tangles", "buildup", "flaky_scalp", "thinning", "definition"]
# These need a person (doctor or dermatologist), not a product list.
MEDICAL_CONCERNS = {"thinning"}
STYLE_GOALS = ["wash_and_go", "twist_or_braid_out", "protective_style", "locs", "short_and_simple", "low_manipulation"]


# ---------- Photo analysis agent ----------

class HairAnalysis(BaseModel):
    """What the photo agent sees in one wash-day photo. Estimates, not diagnoses."""

    is_hair_photo: bool = Field(description="True only if the photo clearly shows a person's own natural hair up close or at medium distance.")
    problem: str | None = Field(default=None, description="If is_hair_photo is false or the photo is unusable, a short, kind reason and what to retake.")
    photo_quality: Literal["good", "fair", "poor"] = "fair"
    curl_pattern: CurlPattern | None = Field(default=None, description="Most likely pattern, 2A-4C. Null if it cannot be judged.")
    alternate_pattern: CurlPattern | None = Field(default=None, description="Second most likely pattern if close, else null.")
    mixed_patterns: bool = Field(default=False, description="True if different sections look like different patterns (very common).")
    pattern_confidence: Level = "low"
    strand_width: Literal["fine", "medium", "coarse"] | None = None
    density: Literal["thin", "medium", "thick"] | None = None
    porosity_estimate: Level | None = Field(default=None, description="Rough guess from visible frizz, shine and dryness. A photo cannot measure porosity.")
    porosity_confidence: Level = "low"
    visible_signs: list[str] = Field(default_factory=list, description="Plain observations such as 'defined spirals', 'dull and dry ends', 'tight shrinkage'.")
    summary: str = Field(default="", description="2-3 friendly sentences for the person, without judging their hair.")


# ---------- What the person tells us ----------

class UserProfile(BaseModel):
    zip_code: str = Field(pattern=r"^\d{5}$")
    curl_pattern: CurlPattern | None = None
    porosity: Level | None = None
    strand_width: Literal["fine", "medium", "coarse"] | None = None
    density: Literal["thin", "medium", "thick"] | None = None
    hair_length: Literal["buzzed_or_very_short", "short", "medium", "long"] = "medium"
    elasticity: Literal["stretches_and_bounces_back", "stretches_and_stays_stretched", "snaps_quickly", "not_sure"] = "not_sure"
    concerns: list[Literal[tuple(CONCERNS)]] = Field(default_factory=list)  # type: ignore[valid-type]
    color_treated: bool = False
    heat_styled: bool = False
    chemically_relaxed_or_bleached: bool = False
    style_goal: Literal[tuple(STYLE_GOALS)] = "wash_and_go"  # type: ignore[valid-type]
    wash_every_days: int = Field(default=7, ge=1, le=30)
    minutes_per_day: int = Field(default=15, ge=5, le=120)
    wash_day_minutes: int = Field(default=90, ge=20, le=360)
    monthly_budget_usd: int = Field(default=40, ge=5, le=500)
    fragrance_free: bool = False
    sulfate_free: bool = False
    silicone_free: bool = False
    notes: str = Field(default="", max_length=MAX_NOTES_CHARS)
    photo_analysis: HairAnalysis | None = None

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str) -> str:
        return " ".join(v.split())[:MAX_NOTES_CHARS]


# ---------- Hair science agent ----------

class ProductNeed(BaseModel):
    category: Category
    max_protein: ProteinLevel = Field(description="The most protein this product may contain for this person.")
    prefer_humectants: bool | None = Field(default=None, description="True prefers glycerin/honey-type ingredients, False avoids them, null no preference.")
    why: str = Field(description="One short sentence.")


class HairScienceReport(BaseModel):
    balance: Literal["needs_moisture", "needs_protein", "balanced"]
    balance_reason: str
    wash_style: Literal["cleanser_plus_conditioner", "mostly_cowash", "gentle_cleanser_only"]
    deep_condition_every_days: int = Field(ge=3, le=30)
    protein_treatment_every_weeks: int | None = Field(default=None, ge=2, le=12, description="Null means no routine protein treatment.")
    clarify_every_weeks: int = Field(ge=2, le=12)
    needs: list[ProductNeed]
    prefer_ingredients: list[str]
    avoid_ingredients: list[str]
    cautions: list[str] = Field(default_factory=list)
    see_a_professional: bool = Field(default=False, description="True when symptoms need a doctor or dermatologist.")


# ---------- Weather agent ----------

class DayWeather(BaseModel):
    date: str
    temp_hi_f: float
    temp_lo_f: float
    dew_point_f: float
    humidity_pct: float
    uv_index: float
    wind_mph: float
    rain_chance_pct: float
    climate: Literal["dry", "comfortable", "muggy", "very_humid"]  # computed in code from dew point


class DayAdvice(BaseModel):
    date: str
    hair_tip: str = Field(description="One short, practical sentence for curly/textured hair that day.")
    humectants: Literal["use", "light", "skip"] = Field(description="Whether glycerin/honey-type products help or backfire that day.")
    hold: Literal["light", "medium", "strong"] = Field(description="Styler hold suited to that day's climate.")
    protect: list[Literal["rain", "wind", "sun", "cold"]] = Field(default_factory=list)


class WeatherAdvice(BaseModel):
    """What the weather agent writes. Code adds the place and the raw numbers."""

    advice: list[DayAdvice] = Field(description="One entry per forecast day, same dates as the forecast.")
    best_wash_dates: list[str] = Field(description="Dates in the next 7 days where drying time and humidity favor a wash day.")
    summary: str = Field(description="Two sentences about the week for this person's hair.")


class WeatherReport(WeatherAdvice):
    place: str
    days: list[DayWeather]


# ---------- Schedule agent ----------

class PlannedDay(BaseModel):
    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    kind: Literal["wash_day", "deep_condition_day", "protein_day", "refresh_day", "rest_day"]
    minutes: int = Field(ge=0)
    what: str = Field(description="One short sentence.")


class ScheduleReport(BaseModel):
    days: list[PlannedDay] = Field(description="Exactly seven days, Mon to Sun.")
    washes_per_month: float
    deep_conditions_per_month: float
    protein_treatments_per_month: float
    refreshes_per_month: float
    notes: str


# ---------- Products agent ----------

class ProductPick(BaseModel):
    category: Category
    product_id: str = Field(description="An id returned by search_catalog. Never invent one.")
    alternate_ids: list[str] = Field(default_factory=list, description="Up to 2 cheaper or similar ids from search_catalog.")
    why: str


class ProductPicks(BaseModel):
    picks: list[ProductPick]
    skipped: list[str] = Field(default_factory=list, description="Categories skipped and why.")


# ---------- Budget agent ----------

class BudgetLine(BaseModel):
    category: Category
    product_id: str
    note: str = ""


class BudgetPlan(BaseModel):
    lines: list[BudgetLine] = Field(description="The final product for each category kept in the routine.")
    dropped: list[str] = Field(default_factory=list, description="Categories dropped to fit the budget, with a reason.")
    swaps: list[str] = Field(default_factory=list, description="Swaps made to save money, e.g. 'X -> Y saves $1.20/month'.")
    summary: str


# ---------- Planner agent (final routine) ----------

class RoutineStep(BaseModel):
    step: int
    action: str = Field(description="Short title, e.g. 'Shampoo scalp'.")
    product_id: str | None = Field(default=None, description="A catalog id, or null for steps without a product (rinse, scrunch, air dry).")
    how: str = Field(description="One or two sentences: amount and technique.")
    minutes: int = Field(ge=0)


class WeekDay(BaseModel):
    """One day of the week plan. Built in code from the schedule and the routine, not written by the model."""

    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    kind: Literal["wash_day", "deep_condition_day", "protein_day", "refresh_day", "rest_day"]
    what: str
    minutes: int
    steps: list[RoutineStep]


class Routine(BaseModel):
    """The planner writes the reusable step lists; code lays them onto the week."""

    headline: str
    hair_profile_summary: str = Field(description="Two sentences describing the person's hair needs, in friendly plain language.")
    wash_day_steps: list[RoutineStep] = Field(description="Full wash-day routine from cleansing to styling.")
    refresh_steps: list[RoutineStep] = Field(description="Quick non-wash day refresh. Empty if the style needs none.")
    deep_condition_steps: list[RoutineStep] = Field(default_factory=list, description="Steps for a deep-condition day (replaces conditioning on that wash).")
    protein_steps: list[RoutineStep] = Field(default_factory=list, description="Steps for a protein treatment day. Empty if no protein treatment is planned.")
    clarify_steps: list[RoutineStep] = Field(default_factory=list, description="One or two steps for a clarifying wash (the clarifier replaces the regular cleanser). Empty if there is no clarifier.")
    why: list[str] = Field(description="3-5 short reasons that tie the routine to the hair profile, weather, time and budget.")
    cautions: list[str] = Field(default_factory=list)


# ---------- Daily check ----------

class TodayPlan(BaseModel):
    action: Literal["wash_day", "refresh", "rest", "protective_care"]
    headline: str
    weather_note: str
    steps: list[RoutineStep]
    tip: str


# ---------- Haircut suggestion (one time, optional) ----------

class HaircutPrefs(BaseModel):
    change: Literal["keep_length", "trim_and_shape", "noticeably_shorter", "much_shorter"] = "trim_and_shape"
    maintenance: Literal["low", "medium", "high"] = "medium"
    goals: list[Literal["shape", "volume_balance", "remove_damage", "easier_styling", "definition", "grow_out"]] = Field(default_factory=list, max_length=6)
    notes: str = Field(default="", max_length=MAX_NOTES_CHARS)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str) -> str:
        return " ".join(v.split())[:MAX_NOTES_CHARS]


class CutOption(BaseModel):
    name: str = Field(description="A plain-language name for the cut, e.g. 'Dry-cut shaped crop'.")
    description: str = Field(description="One or two sentences describing the result, for any gender.")
    why_for_you: str = Field(description="One or two sentences tying it to this person's texture, length, density and upkeep wishes.")
    length_change: str = Field(description="Roughly how much comes off, e.g. 'about 1 inch'.")
    upkeep: str = Field(description="How often to trim or refresh it, and how it grows out.")
    ask_your_stylist: list[str] = Field(description="2-4 short phrases to say to the stylist (techniques and results, not brand names).")


class HaircutSuggestion(BaseModel):
    options: list[CutOption] = Field(description="Two or three different options.")
    avoid: list[str] = Field(description="1-3 things to avoid for this texture and why.")
    stylist_questions: list[str] = Field(description="3-5 questions to ask a salon to check they are comfortable with this texture.")
    bring: list[str] = Field(description="2-4 things to bring or do before the appointment.")
    note: str = Field(description="One sentence: this is guidance based on texture, length and preferences, not face shape; the stylist confirms in person.")
