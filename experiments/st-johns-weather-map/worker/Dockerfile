FROM ghcr.io/astral-sh/uv:0.8.13 AS uv
FROM python:3.13.7-slim-bookworm

COPY --from=uv /uv /uvx /bin/

# No apt ecCodes. cfgrib binds ecCodes through cffi at import time and locates
# the shared library with findlibs, whose first lookup is the ``eccodeslib``
# Python package; the ``grib`` extra below installs that wheel (2.48.0, with
# its own definitions tree), matching the pinned ``eccodes`` bindings instead
# of Debian bookworm's 2.28.0.

WORKDIR /app
ENV PATH="/app/.venv/bin:${PATH}"

# The worker shares the API's pinned dependency set; one lock file keeps the
# two images resolving to the same versions of xarray, cfgrib and zarr.
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra grib

COPY ingest ./ingest
COPY registry/source_data.py ./registry/source_data.py
COPY worker/runtime.py worker/entrypoint.sh ./worker/
RUN chmod 0555 /app/worker/entrypoint.sh

ENTRYPOINT ["/app/worker/entrypoint.sh"]
