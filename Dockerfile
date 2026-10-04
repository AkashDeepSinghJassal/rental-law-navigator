# Rental Housing Law Navigator: React UI + FastAPI + SQLite knowledge base. Not legal advice.
# No API keys are needed at runtime: answers are computed by plain code from the knowledge base.

FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build -- --outDir /ui/dist

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY navigator/ navigator/
COPY web/app.py web/__init__.py web/
COPY web/static/ web/static/
COPY --from=ui /ui/dist web/dist
COPY data/release.db data/release.db
ENV PATH="/app/.venv/bin:$PATH" \
    DATABASE_URL="sqlite:////app/data/release.db" \
    LLM_PROVIDER=anthropic \
    NAVIGATOR_OFFLINE=0
EXPOSE 8080
# PORT is set by Render/most hosts; Fly uses 8080 (fly.toml internal_port)
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]
