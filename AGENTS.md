# Repository Guidelines

## Project Structure & Module Organization
- `project_echo/sel_bot`: Discord agent logic (presence, hormones, memory, prompts). Entry point: `poetry run python -m sel_bot.main`.
- `project_echo/him`: Hierarchical Image Memory FastAPI service (`run_him.py`, planner, storage, vectors). API spec: `project_echo/HIM_Spec_v1.1.md`.
- `project_echo/tests`: Pytest suite covering HIM API, simulation, storage, vector math, and synapse logic.
- `agents/`: pluggable agents; `system_agent.py` handles all system access via LLM understanding.
- `sel_data/` and `project_echo/data/`: local SQLite databases and tiles; treat as runtime artifacts, not canonical sources.
- Docker support via top-level `docker-compose.yml` and `project_echo/Dockerfile`; shell helpers in `start_sel.sh`, `install_sel.sh`, `project_echo/setup.sh`.

## Build, Test, and Development Commands
- Install deps: `cd project_echo && poetry install`.
- Run Discord bot: `poetry run python -m sel_bot.main` (requires env vars below).
- Run HIM API server: `poetry run python run_him.py --data-dir ./data`; profile only: `poetry run python run_him.py --profile-only`.
- Tests: `poetry run pytest`.
- Docker: from repo root, `docker-compose up --build` to start Sel plus Postgres; override `DATABASE_URL` to use SQLite if preferred.

## Coding Style & Naming Conventions
- Python 3.11, 4-space indentation, PEP 8 defaults. Use type hints consistently (matches existing modules) and keep functions pure/deterministic unless clearly documented.
- Snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants and env keys.
- Keep prompts and behavior tuning in `sel_bot/prompts.py` and hormone logic in `sel_bot/hormones.py`; document rationale inline when changing behavioral math.
- Prefer small, well-named modules; maintain current docstring style for public functions.

## Testing Guidelines
- Add/extend tests under `project_echo/tests/test_*.py`; mirror module names where possible.
- Use Pytest fixtures in `project_echo/tests/conftest.py` instead of ad-hoc setup; avoid coupling tests to local `sel_data/` contents—create temporary data dirs as needed.
- When modifying behavior (e.g., response thresholds, storage), add regression tests that pin expected values or API responses.

## Commit & Pull Request Guidelines
- Commit messages: concise, present-tense, and scoped (e.g., `sel_bot: raise image reply chance`, `him: tighten tile eviction`). Avoid multi-scope commits.
- PRs should state intent, summarize behavioral risk, and link issues/experiments. Include command output for tests run; add screenshots/log snippets when UX or API output changes.
- Keep secrets out of commits; supply `DISCORD_BOT_TOKEN`, `OPENROUTER_API_KEY`, and optional `DATABASE_URL` via environment or `.env` ignored files. Document any new env keys in `README.md`.
