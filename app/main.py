"""Isha's Curl Lab API.

Start from the project folder with the venv active:
    uvicorn app.main:app --port 8000
Then open http://localhost:8000
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from app import config
from app.auth import SESSION_COOKIE, read_session_token, router as auth_router
from app.agents import LimitReached, RunContext_, daily_spend, gate
from app.pipeline import UserError, analyze_photo, build_routine, curl_group, replan, suggest_haircut, today_plan
from app.schemas import CurlPattern, HaircutPrefs, HairScienceReport, Level, ProteinLevel, Routine, ScheduleReport, UserProfile, Category
from app.shop import plan_products, store_options

log = logging.getLogger("curl-routine")
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Isha's Curl Lab")
app.include_router(auth_router)


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """The page and its scripts are re-checked on every load, so a fix always shows up (they're small)."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- Spending guards ----------

class RateLimiter:
    """Per-person sliding window (same idea as HW4's chat limit). A person is identified by network address."""

    def __init__(self):
        self.calls: dict[tuple[str, str], deque] = defaultdict(deque)

    def check(self, client: str, kind: str, limit: int) -> None:
        now = time.time()
        q = self.calls[(client, kind)]
        while q and now - q[0] > config.RATE_WINDOW_SECONDS:
            q.popleft()
        if len(q) >= limit:
            wait = int(config.RATE_WINDOW_SECONDS - (now - q[0])) + 1
            raise HTTPException(429, f"You've reached the limit for now. Please try again in about {max(1, wait // 60)} minute(s).")
        q.append(now)


limiter = RateLimiter()


def client_id(request: Request) -> str:
    """Who the rate limit counts: the signed-in account, otherwise the network address (as in HW4)."""
    session = read_session_token(request.cookies.get(SESSION_COOKIE))
    if session:
        return f"user:{session[0]}"
    return request.client.host if request.client else "unknown"


def guard(request: Request, kind: str, limit: int) -> None:
    if not gate.event.is_set():
        raise HTTPException(423, "The app is paused right now. Please try again shortly.")
    if daily_spend.exhausted():
        raise HTTPException(503, "The app has reached its daily usage limit. Please try again tomorrow.")
    limiter.check(client_id(request), kind, limit)


# ---------- Streaming helper ----------

async def stream_run(kind: str, work) -> StreamingResponse:
    """Run `work(ctx)` in the background and stream its progress as one JSON object per line."""
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    ctx = RunContext_(kind=kind, emit=emit)

    async def worker() -> None:
        try:
            await queue.put({"event": "result", "data": await work(ctx)})
        except UserError as e:
            await queue.put({"event": "error", "message": str(e)})
        except LimitReached as e:
            await queue.put({"event": "error", "message": str(e)})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Run %s failed", ctx.run_id)  # details stay in the server log
            await queue.put({"event": "error", "message": "Something went wrong on our side. Please try again."})
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())

    async def lines():
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event) + "\n"
        finally:
            if not task.done():
                task.cancel()  # the person left: stop spending tokens

    return StreamingResponse(lines(), media_type="application/x-ndjson")


# ---------- Routes ----------

@app.get("/api/status")
async def status():
    return {"paused": not gate.event.is_set(), "model": config.MODEL_NAME}


class PauseBody(BaseModel):
    paused: bool


@app.post("/api/pause")
async def pause(body: PauseBody, request: Request):
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Only the person running the app can pause it.")
    gate.event.clear() if body.paused else gate.event.set()
    return {"paused": body.paused}


@app.post("/api/photo")
async def photo(file: UploadFile, request: Request):
    guard(request, "photo", config.PHOTOS_PER_WINDOW)
    raw = await file.read(config.MAX_PHOTO_BYTES + 1)
    if len(raw) > config.MAX_PHOTO_BYTES:
        raise HTTPException(413, "That photo is too large. Please use one under 8 MB.")
    return await stream_run("photo", lambda ctx: _photo(raw, ctx))


async def _photo(raw: bytes, ctx: RunContext_) -> dict:
    analysis = await analyze_photo(raw, ctx)
    return {"analysis": analysis.model_dump(), "run_id": ctx.run_id, "usage": {"agents": ctx.agents, "total": ctx.totals()}}


@app.post("/api/build")
async def build(profile: UserProfile, request: Request):
    guard(request, "build", config.BUILDS_PER_WINDOW)
    return await stream_run("build", lambda ctx: build_routine(profile, ctx))


class HaircutBody(BaseModel):
    profile: UserProfile
    prefs: HaircutPrefs = Field(default_factory=HaircutPrefs)


@app.post("/api/haircut")
async def haircut(body: HaircutBody, request: Request):
    guard(request, "haircut", config.BUILDS_PER_WINDOW)  # one model call, limited like a build
    return await stream_run("haircut", lambda ctx: suggest_haircut(body.profile, body.prefs, ctx))


class TodayBody(BaseModel):
    zip_code: str = Field(pattern=r"^\d{5}$")
    days_since_wash: int = Field(ge=0, le=60)
    wash_every_days: int = Field(ge=1, le=30)
    minutes_today: int = Field(ge=0, le=240)
    routine: Routine


@app.post("/api/today")
async def today(body: TodayBody, request: Request):
    guard(request, "today", config.BUILDS_PER_WINDOW)
    return await stream_run(
        "today",
        lambda ctx: today_plan(body.zip_code, body.days_since_wash, body.wash_every_days, body.minutes_today, body.routine, ctx),
    )


@app.get("/api/catalog/stores")
async def catalog_stores():
    return {"stores": store_options()}


class NeedIn(BaseModel):
    category: Category
    max_protein: ProteinLevel
    prefer_humectants: bool | None = None
    uses_per_month: float = Field(ge=0, le=60)


class RepriceBody(BaseModel):
    """Fine-tune panel: re-pick products from the catalog with no model call."""

    needs: list[NeedIn] = Field(max_length=12)
    hair_length: str = Field(pattern=r"^(buzzed_or_very_short|short|medium|long)$")
    monthly_budget_usd: int = Field(ge=5, le=500)
    curl_pattern: CurlPattern | None = None
    porosity: Level | None = None
    store: str | None = Field(default=None, max_length=30)
    sulfate_free: bool = False
    silicone_free: bool = False
    fragrance_free: bool = False
    essentials_only: bool = False


@app.post("/api/reprice")
async def reprice(body: RepriceBody, request: Request):
    guard(request, "reprice", 60)  # cheap (no model), so a looser limit than builds
    return plan_products(
        [n.model_dump() for n in body.needs], body.hair_length, body.monthly_budget_usd, curl_group(body.curl_pattern),
        body.porosity, store=body.store, sulfate_free=body.sulfate_free, silicone_free=body.silicone_free,
        fragrance_free=body.fragrance_free, essentials_only=body.essentials_only,
    )


class ReplanBody(BaseModel):
    profile: UserProfile
    product_ids: list[str] = Field(min_length=1, max_length=12)
    science: HairScienceReport
    schedule: ScheduleReport
    weather_summary: str = Field(default="", max_length=600)


@app.post("/api/replan")
async def replan_route(body: ReplanBody, request: Request):
    guard(request, "build", config.BUILDS_PER_WINDOW)  # one model call, counted like a build
    return await stream_run("replan", lambda ctx: replan(body.profile, body.product_ids, body.science, body.schedule, body.weather_summary, ctx))


@app.exception_handler(ValidationError)
async def validation_error(_: Request, exc: ValidationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"detail": "Some of those answers didn't look right. Please check the form."})


@app.get("/")
async def index():
    """The page, with each script and stylesheet tagged by its last-change time so browsers never show an old copy."""
    html = (STATIC / "index.html").read_text()
    for name in ("app.js", "styles.css"):
        html = html.replace(f"/static/{name}", f"/static/{name}?v={int((STATIC / name).stat().st_mtime)}")
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
