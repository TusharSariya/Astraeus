.PHONY: config build up down logs test test-api test-web test-registry test-sql spec-validate smoke live-smoke test-layers

config:
	docker compose config --quiet

build:
	docker compose build

up:
	docker compose up --build --wait

down:
	docker compose down

logs:
	docker compose logs --follow

test: test-api test-web test-registry test-sql spec-validate

test-api:
	cd api && uv run pytest

test-web:
	cd web && npm test -- --run && npm run build

test-registry:
	python3 registry/profile_audit.py --strict
	uv run --with-requirements registry/requirements.txt --with pytest python -m pytest registry/tests

# Storage-integrity invariants against a real PostgreSQL. Mocked tests assert
# which statements are sent; only this asserts what the database does with them.
test-sql:
	./scripts/sql-test.sh

spec-validate:
	uv run --project ../../tools/specs python ../../tools/specs/specctl.py validate

# End-to-end against the running stack. Mocked tests cannot catch a fixture
# fallthrough or a truthless readiness check, so these assert the truth
# boundary against real HTTP.
smoke:
	./scripts/smoke.sh

# Opt-in: really contacts upstream providers. Kept out of `test` so a routine
# run never hammers a public good, and never silently depends on the weather.
live-smoke:
	cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke -q

# Opt-in: sweeps every layer of a running stack. Kept out of `test` because it
# needs the Compose stack up, not just the API importable.
test-layers:
	cd api && WEATHER_LAYER_CONTRACT=1 uv run pytest -m layer_contract
