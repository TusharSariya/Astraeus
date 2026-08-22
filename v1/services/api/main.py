from contextlib import asynccontextmanager

from fastapi import FastAPI

from skyfield.api import load

from ephemeris import EPHEMERIS_ID, EPHEMERIS_PATH, EPHEMERIS_SHA256, verify_ephemeris


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Verify only — never download on API boot (see scripts/fetch_ephemeris.py).
    verify_ephemeris()
    yield


app = FastAPI(lifespan=lifespan)

path = verify_ephemeris()          # fails if missing / wrong sha
ts = load.timescale()              # leap seconds / time scales
eph = load(str(path))              # DE442 from disk — no download

sun = eph["sun"]
moon = eph["moon"]
earth = eph["earth"]
print(EPHEMERIS_ID, EPHEMERIS_SHA256[:16], "...", eph)


@app.get("/")
def read_root():
    return {
        "message": "Astraeus API",
        "ephemeris": {
            "id": EPHEMERIS_ID,
            "path": str(EPHEMERIS_PATH),
            "sha256": EPHEMERIS_SHA256,
        },
    }
