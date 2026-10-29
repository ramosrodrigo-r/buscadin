FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini .env.example ./

RUN uv sync --frozen --no-dev

# Optional browser runtime for the private admin's manual company crawlers.
ARG INSTALL_CRAWLER_BROWSER=false
RUN if [ "$INSTALL_CRAWLER_BROWSER" = "true" ]; then uv run playwright install --with-deps chromium; fi

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["python", "-m", "buscadin_bot.main"]
