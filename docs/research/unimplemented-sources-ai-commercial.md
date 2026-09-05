# AI, commercial, and global forecast source audit

2026-09-05. Spec-Impact: none. Read-only research audit; no sources admitted, no credentials accessed, no live operational success claimed. Paths below are relative to `/Users/tusharsariya/Projects/Astraeus`. Registry/adapter status describes the weather-map experiment, not production Astraeus.

## Key finding

WeatherNext 3 and NVIDIA Earth-2 experiments are genuinely missing from ingestion. Google WN3 is not a mistaken name: [Google's current model guide](https://developers.google.com/weathernext/guides/models), checked today and updated 2026-09-04, identifies it and its native total/high/medium/low cloud fractions, 0.1-degree gridded surface output, hourly steps and 64 members. Its station heads have a different 0.05-degree resolution. Access still needs allowlisting. The repository's newer WN3 research supersedes the older SOTA note's recommendation of WN2 for new work.

Earth2Studio is an inference framework, not one forecast source. [NVIDIA's repository](https://github.com/NVIDIA/earth2studio) explicitly separates model/checkpoint/data ownership and provides FCN3 workflows. The researched concrete paths are FourCastNet 1 CPU experiment, FCN3 CPU/GPU experiment, and hosted FourCastNet/NIM. None has an ingest module or registry row. CPU practicality is research, not a measured inference result.

## AI source/model inventory

| Candidate | Implementation finding | Repository evidence / remaining distinction |
|---|---|---|
| Google WeatherNext 3, native GCS Zarr / BigQuery / Earth Engine | Research-only; no registry row or adapter | `docs/research/google-weathernext-3-validation.md:8` and `:125`; authenticated schema sample, local validation, latency/cost study absent. No direct fog/ceiling/visibility variables documented. |
| Google WeatherNext 2 native forecast | Registry-only, credential-required; no adapter | `experiments/st-johns-weather-map/registry/source_data.py:922`; research source `docs/research/sota-models.md:276`. |
| WeatherNext 2 through Open-Meteo | Registry-only, credential-required, intermediary-derived; no adapter | `registry/source_data.py:953` under experiment. Important correction: older `docs/research/wayfinder/aggregator-models.md` says refuse it; current registry records later admission for display-only non-primary use. Clouds are reseller humidity diagnostics, not Google native cloud fields. |
| WN2 self-hosted inference, Mini, WeatherNext Cyclones, Vertex AI managed inference | Research-only generated-method/access variants, not independent centres | `docs/research/sota-models.md:318`; do not count four checkpoints or delivery surfaces as four new sources. |
| NVIDIA FourCastNet 1 local | Research-only, no execution pipeline | `docs/research/nvidia-earth2-cpu-feasibility.md:35`; CPU smoke step not completed. |
| NVIDIA FourCastNet 3 local | Research-only, no execution pipeline | Same `:58`; full CPU inference unverified; no direct clouds/fog/visibility. |
| NVIDIA hosted FourCastNet / dedicated NIM | Research-only paid/account-gated access path | Same `:91`; no adapter or benchmark. |
| NOAA AI-GFS and AI-GEFS | Research-only, no registry or adapter | `experiments/st-johns-weather-map/docs/research/01-atmospheric-nwp-satellite.md:96`; prior anonymous AI-GFS values were observed, AI-GEFS needs its own verification. |
| NOAA OAR AIWP archive: GraphCast, Pangu, FourCastNet v1/v2, Aurora | Research-only archive; no registry or adapter | Same `:100`; researched `noaa-oar-mlwp-data` prefixes preserve model version and GFS/IFS initializer. Prior listing probes are not a local skill study or real-time ingestion. |
| GraphCast / WeatherNext 1 Graph direct/self-run | Research-only legacy baseline | `docs/research/sota-models.md:431`; NOAA-run path is separate from self-hosting and from AIWP archive. |
| GraphCast via Open-Meteo | Refused registry-only row; no adapter | Experiment `registry/source_data.py:2018`; all-null local probe and no run metadata. |
| GenCast / WeatherNext 1 Gen | Research-only legacy baseline | `docs/research/sota-models.md:461`; no inference/ingestion code. |
| Microsoft Aurora including 1.5 and weather/composition/wave/cyclone specializations | Research-only self-run; AIWP output is alternative retrieval route | `docs/research/sota-models.md:493`; experiment atmospheric research `:99`. |
| Pangu-Weather | Research-only academic/self-run, license caveat in research | `docs/research/sota-models.md:527`; AIWP output route must retain its own provenance and terms review. |
| NeuralGCM | Research-only; explicitly low near-term value | `docs/research/sota-models.md:576`; coarse hybrid research model. |
| FuXi, FengWu, ArchesWeather | Research-only; no verified open forecast route in research | Experiment atmospheric research `:102`. |
| WindBorne WeatherMesh forecasts and Atlas balloon observations | Research-only commercial/uncertain access | Same `:106`; distinct forecast versus observational products. |
| Silurian GFT / Earth API | Research-only commercial | Same `:103`; no adapter/registry. |
| Jua EPT-2e | Research-only commercial | Same `:104`; no adapter/registry. |
| Brightband, Excarta | Named commercial/research candidates; no verified open feed | Same `:105`; no adapter/registry. |
| ECMWF AIFS Single | Existing registry, but no concrete adapter registration found | Experiment `ingest/adapters/ecmwf_opendata.py` registers IFS at `:150`, AIFS ENS at `:635`, IFS ENS at `:636`; older research's claim all are native is not proof Single works. Cross-check root registry audit. |
| ECMWF AIFS ENS | Partial adapter: assembly exists, discovery always raises; explicitly not schedulable by default | Experiment `ingest/adapters/ecmwf_opendata.py:610`, `:635`; `ingest/adapters/__init__.py:28`, and `ecmwf_opendata.py:390`; discovery is unimplemented even after scheduling admission, so this cannot ingest automatically. |
| AIFS ENS via dynamical.org Icechunk/Zarr | Research-only alternate delivery, not new model | Experiment atmospheric research `:101`; exact store path not verified in prior note. |
| ECCC `model_gdps-geml` | Research watch item; empty directory in prior probe | Experiment atmospheric research `:62`; don't infer an actual model product from directory name. |

No research mention of CorrDiff or StormCast was found in the repo-wide Markdown search; they should not be invented as previously identified requirements merely because Earth2Studio's modern vendor catalogue includes additional models. `forecastNet` is explicitly excluded: `docs/research/nvidia-earth2-cpu-feasibility.md:106` identifies a generic time-series architecture without operational weather inputs or checkpoints. Earth2Studio and Anemoi are tooling, not extra weather centres.

## Commercial environmental providers, all without ingestion implementations

| Provider/product | Current disposition/evidence |
|---|---|
| Meteomatics including source-selected models, vertical/cloud fields and Meteodrone observations | Research-only; proposed first paid trial. `docs/research/paid-environmental-apis.md:228`, `:588`. |
| Tomorrow.io including proprietary radar/microwave observations | Research-only; contract and local bake-off needed. Same `:293`, `:312`, `:594`. |
| Google Air Quality | Research-only; surface health/AQ product, not atmospheric optical transmission. Same `:347`. |
| Ambee | Research-only. Same `:392`. |
| IQAir / AirVisual | Research-only sensor/AQ aggregation. Same `:422`. |
| Vaisala instruments, including ceilometer/fog/visibility hardware | Research-only local measurement investment, not regional forecast feed. Same `:451`. |
| Xweather / AerisWeather | Research-only. Same `:493`. |
| Visual Crossing, Weatherbit, OpenWeather | Research-only; contract restrictions documented separately in experiment commercial research. Same `:499`. |
| Windy Point Forecast | Research-only alternate delivery with model/provenance/terms limits. Same `:506`. |
| Spire radio-occultation / weather | Research-only. Same `:512`. |
| DTN | Research-only. Same `:520`. |
| Meteoblue, Stormglass | Research-only commercial named candidates. `docs/research/wayfinder/aggregator-models.md` section “Named and not pursued”. Meteoblue seeing/transparency packages are a separate topic for other audit agent. |
| Meteosource | Registry-only citation/paid-provider catalogue, deliberately no adapter. Experiment `registry/source_data.py:1073`. |
| Weatherstack, Foreca, StormGeo | Research-only, prior research declines them on access/value grounds. Experiment `docs/research/03-local-climate-commercial.md:918`. |

## Global/regional forecast additions and false positives

`docs/research/north-atlantic-forecast-model-viability.md:50` distinguishes RAP/NAM/RRFS candidates from out-of-domain products. RAP is registry-only (`registry/source_data.py:1094`); NAM parent is also registry-only (`registry/source_data.py:1111`, `noaa-nam`); conditional RRFS-NA remains research-only pending actual implementation/validation. A prior one-off full-box RAP/NAM response is not an ingestion adapter.

JMA GSM (`registry/source_data.py:1854`), ARPEGE World (`:1884`), UKMO Global deterministic (`:1914`) are registry-only Open-Meteo paths without an Open-Meteo ingest module. Their research probes do not mean implementation. UKMO Global ensemble is a separate research-only candidate with null probe results (`01-atmospheric-nwp-satellite.md:39`). CMA GRAPES and KMA GDPS are refused/problematic registry candidates (flat-zero clouds and stale/all-null respectively), not ordinary implementation backlog. Bright Sky/DWD MOSMIX station 71801 is additional registry-only point weather/visibility evidence (root registry audit should cite row).

DWD ICON Global has a concrete stub which **always raises** `AdapterUnavailable` (`ingest/adapters/dwd_icon.py:67`, `:85`, `:88`). It is partially wired, not a working source. ICON EPS is another no-adapter family. ECMWF IFS is a registered nonpublishing stub: both discovery and fetch always raise (`ingest/adapters/ecmwf_opendata.py:143`, `:146`). IFS ENS and AIFS ENS have partial member assembly implementations, but discovery always raises even if scheduling is enabled (`:390`); both therefore remain incomplete ingestion paths. None should be counted as operational simply because an adapter class exists.

MET Norway locationforecast/seamless is a researched aggregator/global fallback, not a new Newfoundland regional model (`01-atmospheric-nwp-satellite.md:43`). SEAS5, EC46, CanSIPS are longer-horizon research candidates (`:45`, `:46`, `:61`) rather than near-term clouds. HRRR, NBM, AROME/MEPS/Nordic/Icelandic/Greenlandic/Iberian regional systems have no verified full-box coverage in research and should be listed separately as excluded/coverage-unproven, not implied implementation commitments. Russian products remain underspecified, without an exact named product, per north-Atlantic viability `:67`.

## Evidence boundaries

Searched Python/YAML/TOML implementation for AI model/provider terms and inspected ingest adapter imports and actual registrations. Research-only absence means no matching concrete ingest adapter/model pipeline found in this checkout; it does not imply no draft spec or no UI citation. Root registry audit should provide canonical exact record statuses and live report evidence. No operational endpoints were polled during this audit. Official web checks were limited to identifying WeatherNext 3 and Earth2Studio; older procurement/access assertions remain dated repository research, not current legal findings. Reanalysis, satellite, space-weather, environmental observations, historic archives and other runnable physical/radiative models are assigned to other agents and not exhausted here.

Existing planning artifact: `experiments/st-johns-weather-map/openspec/changes/optional-north-atlantic-models/` already contains proposal/design/tasks/spec text, including Earth2 and WeatherNext 3, with implementation tasks unchecked (root agent verified). Therefore these are researched and proposed, not wholly unplanned; no need to recreate a proposal blindly. Its broad “adapter-backed” language for IFS/ENS/AIFS/ICON must be reconciled with actual registration and stub behavior above.
