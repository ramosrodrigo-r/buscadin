# Repository Guidelines

## Project Structure & Module Organization

`PRD_Buscadin_Telegram_Bot.md` defines the Buscadin Jobs Bot MVP. The application lives under `src/buscadin_bot/`, with configuration and entry points in `config.py` and `main.py`, persistence in `db/`, source connectors in `sources/`, domain workflows in `services/`, Telegram integration in `telegram/`, and administrative tooling in `cli.py`. Keep database migrations in `migrations/` and automated tests in `tests/`. Store local SQLite data under `data/` and never commit it. Delivery reports belong in `docs/entregas/`, with roadmap state in `.planning/`.

## Build, Test, and Development Commands

Use Python 3.12+ and `uv`:

```bash
uv sync                              # Install locked dependencies
uv run pytest                        # Run the test suite
uv run pytest tests/test_himalayas.py  # Run focused source tests
uv run python -m buscadin_bot.main   # Start polling and collection
uv run alembic upgrade head          # Apply migrations
```

Keep collection intervals, Telegram credentials, database URLs, and notification limits in environment variables. Do not add Redis, Celery, or a bot framework to the MVP.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, small async functions, and clear domain names. Prefer `snake_case` for modules, functions, and variables; `PascalCase` for classes; and uppercase names for environment settings. Keep source connectors behind the `JobSource` interface and isolate Telegram HTTP calls behind the official Bot API client. Run `uv run pytest`; format and lint with tools declared in `pyproject.toml` when they are added.

## Testing Guidelines

Use pytest, pytest-asyncio, and mocked HTTP responses. Name files `test_*.py` and tests `test_<behavior>`. Cover normalization, deduplication, eligibility classification, idempotent callbacks/outbox delivery, retry behavior, and referral validation. Tests must not call real Telegram or job-source APIs and should run with `uv run pytest`.

## Security & Configuration

Never commit `.env`, bot tokens, or credentials, and never log them. Enforce the configured admin chat/user IDs for every command and callback. Escape external content before Telegram HTML formatting, use timeouts and backoff, and do not infer affiliate URLs or Brazil eligibility.

## Commit & Pull Request Guidelines

No Git history is present yet, so no existing commit convention can be inferred. Use short imperative subjects such as `Add Himalayas source` and keep commits focused. Pull requests should explain behavior changes, include tests and migration notes, document configuration changes, and attach relevant Telegram message screenshots when notification formatting changes.
