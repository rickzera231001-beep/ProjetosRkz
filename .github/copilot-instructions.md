This project is an RPA-based data collection + evaluation tool for football matches
and bookmaker odds. The instructions below give an AI coding agent the minimal,
actionable context to be productive quickly.

1) Big picture
- Purpose: collect stats and odds from configured sites/leagues, evaluate matches
  with local heuristics or OpenAI, and output recommendations. See [README.md](README.md).
- Key entrypoints: `runner.py` (full workflow with leagues/odds/parlays) and
  `projetos.py` (simpler runner). Prefer `runner.py` for the complete pipeline.
- Core modules:
  - `rpa_scraper.py`: scraping utilities and extraction helpers (SofaScore helpers,
    fetch_html fallback, `scrape_stats`, `scrape_odds`).
  - `rpa_playwright.py`: Playwright-based fetch fallback for JS-heavy sites.
  - `ai_eval.py`: evaluation logic (`evaluate_matches`, `generate_parlays`).
  - `scripts/`: useful one-off scripts and tests (see `scripts/test_match.py`).

2) Config and runtime behavior
- Config files: `config.local.yaml` overrides `config.yaml`. `runner.py` checks
  for `config.local.yaml` first. Edit `sites` and `leagues` sections there.
- Important config keys the agent should read/modify when implementing features:
  - `sites`: list of dicts with `name`, `url`, `type` (e.g. `bookmaker`),
    `stats_selectors`, `odds_selectors`.
  - `leagues`: used for SofaScore discovery (`source: sofascore`, `url`, `max_teams`).
  - `openai`: `{use_openai, api_key}` — runner prefers env var `OPENAI_API_KEY`.
  - `value_detection` and `output.json_file` — controls parlays detection & output.

3) Developer workflows & commands
- Create venv and install deps:
  - `python -m venv .venv`
  - `.\.venv\Scripts\Activate.ps1` (PowerShell)
  - `pip install -r requirements.txt`
- Playwright (optional for JS sites): `pip install playwright` then `playwright install`.
- Run main pipeline: from project root run `python runner.py` (outputs recommendations
  to stdout; `runner.py` can save JSON if `output.json_file` is set).
- Debugging scraping failures: runner writes `scrape_error_<site>.html` or `.txt`.
  Use those saved files to inspect returned HTML.

4) Project-specific conventions and patterns
- Fallback strategy: `rpa_scraper` exceptions trigger a Playwright fallback in
  `runner.py` (imports inside the except block). Implement similar safe imports
  when adding new optional dependencies.
- Broad try/except usage: many workflows swallow errors and continue; prefer
  targeted exception handling when changing logic to avoid hiding regressions.
- Naming: saved debug files follow `scrape_error_<name>.*`. Keep this pattern
  when adding new error dumps.
- Bookmaker matching: `sites` entries with `type: bookmaker` are iterated to find
  odds for discovered matches — preserve that lookup when changing match/odds logic.

5) Integration points & data locations
- Data files: `data/` contains pre-collected JSON (e.g., `paulistao_*`). Use
  these for offline analysis or unit tests.
- Scripts under `scripts/` implement focused tasks (fetching, cleaning, tests).
  They can be run directly with `python scripts/<name>.py`.

6) Helpful examples to edit or reference
- To add a new scraping target, update `config.local.yaml` `sites` with
  `stats_selectors`/`odds_selectors` and extend helpers in `rpa_scraper.py`.
- To change evaluation, modify `ai_eval.py` functions `evaluate_matches`
  and `generate_parlays` (these are called by `runner.py`).

7) Tasks an AI agent can immediately perform
- Add small scraper for a new bookmaker: update `config.local.yaml`, add selector
  mapping in `rpa_scraper.py`, and add an example test under `scripts/`.
- Harden error handling: replace broad exceptions with specific ones in
  `runner.py` and `rpa_scraper.py` where appropriate.
- Add unit tests that load files from `data/` and assert scraper output shapes.

If anything above is unclear or you want the file to emphasize different internals
(e.g., more code links or a run script), tell me which parts to expand or correct.
