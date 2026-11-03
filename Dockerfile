FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini .env.example ./
RUN uv sync --frozen --no-dev
RUN useradd --uid 10001 --create-home buscadin && mkdir -p /app/data && chown -R buscadin:buscadin /app/data /home/buscadin
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
USER buscadin

# Browser-only worker. Deployment supplies the sandbox security profiles.
FROM runtime AS crawler
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN playwright install --with-deps chromium
USER buscadin
ENV HOME=/tmp/home XDG_CONFIG_HOME=/tmp/config XDG_CACHE_HOME=/tmp/cache
CMD ["python", "-m", "buscadin_bot.web.crawler"]

# Default image: admin/portal without any Chromium executable.
FROM runtime AS app
EXPOSE 8080
CMD ["python", "-m", "buscadin_bot.main"]
