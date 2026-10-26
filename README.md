# Isha's Curl Lab: a routine builder for textured hair

A website that builds a personal hair-care routine for **waves, curls, coils, locs, braids and short hair** (2A to 4C, any gender, any budget), based on the person's hair, their local weather, their time and their monthly budget. Every product is a real, US-sold product from a verified catalog, and every price and monthly cost is computed, not guessed.

A team of nine AI agents (all `gpt-6-luna` through Portkey) does the work. Plain code checks the result before anyone sees it.

| Agent | Job |
|---|---|
| Photo reader | Optional: reads a wash-day photo and estimates curl pattern (2A-4C), strand width, density and porosity, with a confidence level. Never guesses anything about the person. |
| Hair scientist | Protein vs. moisture balance, porosity needs, wash and conditioning cadence. |
| Weather watcher | Reads the 7-day forecast (dew point, rain, wind, UV) and turns it into hair advice. |
| Schedule planner | Fits wash days to the person's week and available minutes. |
| Product finder | Searches the verified product catalog. |
| Budget keeper | Fits the picks to the monthly budget. |
| Routine planner | Writes the step-by-step routine. |
| Haircut stylist | Optional, one time: two or three haircut ideas from the intake, texture-based and never face-shape-based. No salon or brand is ever named. |
| Daily coach | On any later day, decides what to do today from the saved routine and today's weather. |

Hand-offs: `hair scientist + weather` → `schedule + products` → `budget` → `planner` → checks. Details, tokens and costs are in the report.

## Run it (about 5 minutes)

You need **Python 3.10 or newer** and a **Portkey API key** that can call `gpt-6-luna`. No Node, no database to install.

```bash
git clone <this repo's URL>
cd <repo folder>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and put your key after `PORTKEY_API_KEY=`.

**Where the key goes:** the app looks for `.env` in this repo's folder first, then in the folder above it. So if your `.env` already sits one level up (next to the cloned repos), you can skip the `cp` step.

Start the app:

```bash
uvicorn app.main:app --port 8000
```

Open **http://localhost:8000**. A routine takes about 40 seconds to build and costs roughly half a cent.

To try it quickly: *Build my routine* → *Skip the photo* → pick a curl pattern → *Next* → enter any US ZIP code (for example `06511`) → *Build my routine*.

### Optional accounts

Signing in is optional. Guests keep their routine in the browser. Creating an account saves the profile and latest routine on the server (in `data/app.db`, created on first use and ignored by git) so it can be opened on any device. Photos are never stored.

### Tests

```bash
python -m pytest -q tests
```

These 28 tests need no API key and make no model calls. They cover ingredient analysis, budget rules, the product validator, spending guards, accounts, and the budget/store/ingredient picker.

### Evaluation scripts (these call the model; about 5 cents each)

```bash
python scripts/run_eval.py             # 10 varied profiles, every result checked by code
python scripts/compare_plain_llm.py    # the same profiles asked of plain gpt-6-luna, no tools
```

Results are written to `output/eval/`.

## What you can do in the app

- **Build a routine** from a questionnaire, with an optional photo step.
- **Today:** a saved routine plus today's forecast tells you what to do today (wash, refresh, rest or protect).
- **This week:** a seven-day plan with every step, product and minute count.
- **Products & cost:** per-product price, cost per use and monthly cost. A **fine-tune panel** has a budget slider (the products re-pick instantly), a one-store filter, sulfate/silicone/fragrance filters, an essentials-only switch and sorting. *Use these in my routine* has the planner rewrite the steps around the new products.
- **Haircut:** a one-time suggestion of haircut options for the person's texture, search links for stylists near their ZIP code (Google Maps and Yelp), and a drafted appointment request built from the days and times they are free. The app cannot call or book for you: copy the message into the salon's form, email or text.
- **Behind the scenes:** how many helpers worked, how long it took and what it cost, in plain language.

## Safety, in short

- **Catalog only:** every product id is checked against the verified catalog; an invented one is rejected (the planner gets one retry, then the id is removed). Prices and totals are computed by code.
- **Prompt injection:** profile notes and any text in a photo are treated as information, never instructions, in every agent's prompt. Tested with a hostile note and a hostile photo (see `output/eval/`).
- **Overspending:** each build is capped at 20 model requests, 45 tool calls and 60,000 tokens; every response at 2,000 tokens. Each person gets 5 builds and 5 photo checks per 10 minutes, and the whole app stops at 2,000,000 tokens a day. A pause switch (`POST /api/pause`, local machine only) holds all runs.
- **Audit trail:** every agent step is appended to `output/audit_trail.json` (kept 90 days, values cut at 500 characters). It is not committed.
- **Medical:** thinning, sores or severe itching trigger a "see a doctor or dermatologist" message instead of product advice.
- **Accounts:** Argon2id password hashes, 5 failed logins lock an account for 15 minutes (unknown emails too), a signed HttpOnly session cookie, and the same generic "Incorrect email or password" message for every failure.
- **Photos:** checked to be real images, stripped of metadata, shrunk, analyzed in memory and never saved.

## The product catalog

`data/products.json` holds 65 US hair products (cleansers, clarifiers, co-washes, conditioners, deep conditioners, protein treatments, leave-ins, creams, gels, mousses, oils and scalp care). Each entry has its exact ingredient list, size, a price, and the retailers where it was seen. Protein, sulfate, silicone and fragrance flags are computed from the ingredient lists by `app/ingredients.py`, never typed by hand.

Prices are snapshots from **2026-10-25** and can change; the app shows how old each price is. To add products, append entries with the same fields to `data/products.json`.

## Repo layout

```
app/
  main.py          FastAPI routes: build, photo, today, haircut, reprice, replan, accounts
  agents.py        the nine agents, the shared runner (limits, audit, pause switch)
  pipeline.py      who hands off to whom, plus the plain-code validators
  shop.py          budget slider logic: swaps, drops, upgrades, store filter
  tools.py         catalog search, cost math, weather (ZIP lookup + Open-Meteo, no keys)
  ingredients.py   ingredient list analysis
  catalog.py       catalog loader and cost per use
  auth.py          optional accounts
  prompts/         one prompt file per agent (read on every run)
  static/          the web page (HTML, CSS, JavaScript; no build step)
data/products.json the verified catalog
scripts/           evaluation scripts
tests/             tests that need no API key
output/            evaluation results, sample runs, report assets
report.html        the written report
slides.html        the slide deck
```

## Notes and limits

- The weather uses two free services that need no key (zippopotam.us and Open-Meteo). If they are down, the routine is built without weather and says so.
- A photo cannot measure porosity. The photo agent gives an estimate with a confidence level, and the app suggests a quick strand test to confirm.
- The catalog is a snapshot of 65 products, not every product sold.
- This app gives hair-care guidance, not medical advice.
