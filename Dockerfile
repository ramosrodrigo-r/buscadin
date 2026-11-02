FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini .env.example ./

RUN uv sync --frozen --no-dev

# Admin deployments require Chromium. Portal-only builds may explicitly opt out.
ARG INSTALL_CRAWLER_BROWSER=true
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN if [ "$INSTALL_CRAWLER_BROWSER" = "true" ]; then uv run --no-dev playwright install --with-deps chromium; fi
RUN useradd --uid 10001 --create-home buscadin && mkdir -p /app/data /opt/playwright && chown -R buscadin:buscadin /app /opt/playwright /home/buscadin

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
USER buscadin
RUN if [ "$INSTALL_CRAWLER_BROWSER" = "true" ]; then python scripts/check_browser_runtime.py; fi
CMD ["python", "-m", "buscadin_bot.main"]
