# Sample runs

Curated step-by-step traces taken from the app's audit trail (`output/audit_trail.json`, which is not committed because
real users' runs would land in it). Each file lists every agent step: model turns, tool calls with their arguments, tool
results and outputs (values over 500 characters are cut), with token counts and cost per agent in each `run_end`.

- `build_run_for_the_report_screenshots.json`: the full routine build shown in the report (4B, high porosity, $35, ZIP 06511).
- `daily_check.json`: a daily check (weather agent, then daily coach).
- `photo_refused_as_not_hair.json`: the photo agent refusing a hostile non-hair image.
- `haircut_suggestion.json`: the one-time haircut suggestion.
- `hostile_note_run.json`: a build whose profile note tried to hijack the agents.

The test ZIP code 06511 is a public New Haven ZIP; no personal data is in these files.
