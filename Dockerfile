FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends graphviz fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.9.18
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/ backend/
RUN uv sync --frozen --no-dev --no-editable
COPY examples/ examples/
COPY --from=frontend /web/dist frontend/dist/
RUN groupadd --gid 10001 docagent && useradd --uid 10001 --gid 10001 --create-home docagent \
    && mkdir -p /data && chown -R docagent:docagent /app /data
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 DOCAGENT_DATA_DIR=/data
USER docagent
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"
CMD ["uvicorn", "docagent.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
