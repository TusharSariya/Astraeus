FROM ghcr.io/astral-sh/uv:0.8.13 AS uv
FROM python:3.13.7-slim-bookworm

COPY --from=uv /uv /uvx /bin/

# The API imports ``ingest`` and ``registry`` from the experiment root, so the
# image mirrors the repository layout: /app is the root, /app/api the project.
WORKDIR /app/api
ENV PATH="/app/api/.venv/bin:${PATH}" \
    PYTHONPATH=/app

COPY api/pyproject.toml api/uv.lock ./
# Timestamp-demand model queries decode one selected native GRIB response in
# the API's locked child process, so this image needs the same pinned ecCodes
# runtime as the worker.  The derive extra remains worker-only.
RUN uv sync --frozen --no-dev --no-install-project --extra grib
COPY ingest /app/ingest
# The catalogue modules only, not the tests or fixtures: ``weather_api.models``
# and ``ingest.manifest`` import ``registry.fields``, ``store`` imports
# ``registry.source_data``, and ``fields.schema.json`` travels with the
# catalogue it describes.
COPY registry /app/registry
COPY api/weather_api ./weather_api
RUN uv sync --frozen --no-dev --extra grib

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "weather_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
