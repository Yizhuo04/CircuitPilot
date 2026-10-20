FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home circuitpilot
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY alembic.ini ./
RUN uv sync --locked --no-dev --no-editable \
    && mkdir -p /app/data/uploads && chown -R circuitpilot:circuitpilot /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 CIRCUITPILOT_AUTO_CREATE_SCHEMA=false
USER circuitpilot
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3)"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
