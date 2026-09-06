# IERS time inputs and selected NAIF kernel evidence

Captured 2026-09-06 for issue #123. This is non-normative research. The implementation remains isolated, unregistered and `operational: false`; it performs no Earth-orientation, time-scale, frame, or ephemeris computation.

## Product selection and identity

The selected IERS Earth-orientation product is [`finals2000A.all`](https://datacenter.iers.org/data/9/finals2000A.all). [IERS version metadata](https://datacenter.iers.org/versionMetadata.php?filename=latestVersionMeta%2F9_FINALS.ALL_IAU2000_V2013_019.txt) identifies it as the daily IAU 2000A Bulletin A rapid/prediction series, with Bulletin B final values where available. The authoritative [fixed-width format](https://maia.usno.navy.mil/ser7/readme.finals2000A) defines calendar date, MJD UTC, three independent IERS/prediction flags, Bulletin A polar motion/error in arcseconds, UT1-UTC/error in seconds, LOD/error in milliseconds, dX/dY/error in milliarcseconds, and optional Bulletin B polar motion, UT1-UTC, dX and dY. Every field is stored with these units; blank optional values stay missing.

The selected IERS civil-time authority is [`Leap_Second.dat`](https://hpiers.obspm.fr/iers/bul/bulc/Leap_Second.dat). Its complete schema is effective MJD UTC, effective calendar date, and TAI-UTC seconds, plus the header's Bulletin update and expiration identities. An expired table fails closed.

The selected supplementary NAIF kernel is the exact generic LSK [`naif0012.tls`](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls), not the mutable `latest_leapseconds.tls` alias. NAIF's [LSK directory note](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/aareadme.txt) identifies NAIF0012 and says the latest aliases currently resolve to it. Stored fields are `DELTET/DELTA_T_A`, `DELTET/K`, `DELTET/EB`, both `DELTET/M` coefficients, and all `DELTET/DELTA_AT` offset/effective-UTC pairs. They are retrieval evidence only and are not loaded into a toolkit or used for a calculation.

No Earth PCK is selected. NAIF's [generic PCK inventory](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/aareadme.txt) offers materially different choices: a frequently regenerated high-accuracy EOP kernel, historical, low-accuracy long-term prediction, and combined products. They differ in coverage, reconstructed/predicted boundaries and UT1 treatment. The same note warns that the current generic text PCK changes some body rotation models materially. Choosing a PCK therefore requires an owner-approved scientific use, required frame, time interval and accuracy policy. Issue #123's selected supplementary path is complete with the LSK; PCK adoption remains an explicit optional blocker, outside this selection. DE442 remains the existing implementation; DE440/441 and SPICE software toolkits are excluded.

## Exact retained HTTP evidence

The finite ceilings were 4 MiB for finals2000A and 64 KiB for each text file, with 38 GiB free before capture. Payloads, response headers, precise post-body UTC timestamps, normalized artifacts, receipt, and actual FastAPI readback remain in `/private/tmp/astraeus-iers-time-capture` for owner review. Raw payloads and rebuilt artifacts are not committed.

| Product | Actual capture UTC | Bytes | SHA-256 | HTTP identity |
|---|---:|---:|---|---|
| finals2000A.all | `2026-09-06T03:57:17.963183Z` | 3,764,888 | `80119694522717471744a78b28bc872e998523f8b1e2007424f9cd08af7ac4c6` | Last-Modified `Thu, 03 Sep 2026 17:46:08 GMT`; Content-Length `3764888` |
| Leap_Second.dat | `2026-09-06T03:57:18.425361Z` | 1,352 | `6cb6f5d4b819f2e568e25db4b0b26d89dedf031fdffb18bc94d40f4e94e268d7` | Last-Modified `Mon, 06 Jul 2026 07:52:10 GMT`; ETag `"548-655ec8d416c41"`; expires `2027-06-28` |
| naif0012.tls | `2026-09-06T03:57:18.932859Z` | 5,257 | `678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b` | Last-Modified `Fri, 15 Jul 2016 00:00:37 GMT`; Content-Length `5257`; exact `NAIF0012` identity confirmed by the 792-byte directory note, SHA-256 `08c828ec92a0ff465f4184a6cd97968cf32e8e1e4e8e7411eb96d795308fbf8f`, captured `2026-09-06T03:57:19.431429Z` |

The committed replay command is:

```sh
uv run --project api python scripts/capture-iers-time.py \
  /private/tmp/astraeus-iers-time-capture \
  /private/tmp/astraeus-iers-time-capture/final-verifiable
```

It reproduced artifact hashes `a05d0da4...` (21,369 bytes), `aca5e184...` (3,365 bytes), and `d12d6974...` (2,283 bytes), then injected those staged, explicitly nonpublishable artifacts into a test store and read them through `LiveStore` and `GET /api/experiments/weather/v0/experimental/time-inputs`. The HTTP response returned the exact retrieval-completion times (the LSK transaction completes with its identity note at `2026-09-06T03:57:19.431429Z`), 21 finals variables including the three observed/predicted status fields, both IERS leap variables, the NAIF DELTA_AT series, kernel version and DELTET constants. Direct parser-to-HTTP comparison checked 168 finals values/flags, 56 IERS leap values and 28 NAIF offsets with zero mismatches. For the live finals window it returned eight daily UTC epochs from `2026-09-01` through `2026-09-08`; IERS rows switch from observed to predicted on `2026-09-04`, and the HTTP values preserve that distinction.

All three `RunResult` objects deliberately return `complete: false` and `qc_passed: false`. The accepted `RunManifest` contract only validates catalogued evidence fields and has no reference-input shape for these unregistered products. Their provenance records `publishable: false` and the missing contract instead of claiming an exception. The API proof therefore demonstrates readback of the staged immutable bytes, not worker publication or admission.
