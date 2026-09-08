# Running the map-first workbench

Run these commands from the experiment directory **inside the worktree that
contains PR #306**, currently:

```sh
cd /Users/tusharsariya/Projects/Astraeus-map-first/experiments/st-johns-weather-map
make workbench-api-up
make workbench-web
```

The frontend is http://127.0.0.1:5197. Its API is http://127.0.0.1:8197.
The web target refuses to silently choose another port. If that frontend is
already running, use its existing page; stop its terminal process before
starting a replacement.

The normal local storage stack must already be up. The isolated API joins its
existing `astraeus-st-johns-weather_weather` network and uses its PostgreSQL and
object store. It has a separate Compose project, image and container, so a rebuild
of the main checkout cannot replace this worktree's API. Stopping the storage
stack still temporarily makes stored data unavailable; bring storage back before
using the workbench. No second database or ingestion worker is started by this
target.

To rebuild the workbench API after source changes, repeat `make workbench-api-up`.
To stop just that API, use `make workbench-api-down`.

## Why make down/up appeared to undo a fix

`make up` **does** pass `--build`. It builds the files in the checkout where it is
run. During the September 8 investigation, the regular `Astraeus` checkout was
at `9af2aaf`, while the workbench changes were on `fix/map-first-workbench` in
`Astraeus-map-first`. Rebuilding the former correctly recreated older code. The
previous handoff gave a frontend port without making that distinction clear.
This was a checkout/runtime mismatch, not Docker failing to rebuild.

The regular checkout's uncommitted work has not been moved or overwritten.
After the PR is merged and that checkout is updated, the usual `make up` will
build the merged version there too.

## Bounded live catalogue check

```sh
python3 scripts/check-layer-inventory.py
python3 scripts/check-layer-inventory.py --fetch-images
```

The first checks every sample, frame and image timestamp across all five
catalogue variants against the API's serving window. The second additionally
requests one 256×256 image per available layer, at most 32 images with two
concurrent requests. It does not request point forecasts or start ingestion.
Provider failures remain reported independently of time-window violations.
