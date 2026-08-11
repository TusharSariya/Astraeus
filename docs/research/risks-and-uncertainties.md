# Astraeus risks and uncertainties

Last reviewed: 2026-08-10

## Executive conclusion

Astraeus can be engineered with the sources and tooling identified in this
research dossier. The largest risk is not implementation feasibility. It is
building a sophisticated optimizer that returns precise-looking rankings
without enough evidence that location B will genuinely offer better observing
conditions than location A.

The failure mode to avoid is:

> A polished decision system that is internally consistent, explainable, and
> precisely wrong.

The first major investment should therefore be a scientific feasibility and
forecast-ranking experiment, not a complete product build.

## Risk register

| Rank | Risk | Severity | Current confidence | Principal mitigation |
| ---: | --- | --- | --- | --- |
| 1 | Small-scale cloud and fog are not forecastable well enough to support travel decisions | Existential | Low | Prospective Atlantic Canada forecast bake-off |
| 2 | Observation ground truth is too sparse, biased, or ambiguous for validation | Existential | Low | Instrumented sites and explicit attempted-observation labels |
| 3 | Aurora model output cannot be mapped reliably to local apparent visibility | High | Low | Optical validation and conservative categorical outputs |
| 4 | Heuristic scoring creates false precision and unstable rankings | High | Medium | Gates, uncertainty bands, ranking-stability tests, restrained UX |
| 5 | Historical forecast vintages are unavailable or confused with reanalysis | High | High that the gap exists | Begin immutable self-archiving immediately |
| 6 | Recommended sites are obstructed, closed, private, or unsafe | High | Medium | Curated sites, access evidence, runtime checks, explicit unknowns |
| 7 | Users cannot act before the forecast or clearing changes | High | Low | Travel-aware value-of-moving and recommendation-stability rules |
| 8 | Directional light-pollution proxies do not represent actual sky brightness | Medium | Low | Local SQM/all-sky validation and conservative penalties |
| 9 | Paid providers add convenience but no measurable forecast skill | Medium | Low | Blind, archived comparison against the open baseline |
| 10 | The synthesized recommendation does not change user behaviour enough to support a product | Existential product risk | Low | User testing with real go/stay/move decisions |

Severity describes product consequence, not the probability that the risk will
occur. `Current confidence` describes confidence in Astraeus's ability to
control the risk with currently available evidence.

## 1. Small-scale cloud and fog forecastability

This is the central scientific risk.

Atlantic Canadian astronomical visibility can depend on:

- narrow marine-fog boundaries;
- coastal stratus and terrain-induced low cloud;
- small openings in multilayer cloud;
- fog onset and clearance timing;
- thin or optically variable high cloud;
- a cloud layer intersecting a low-elevation viewing ray tens or hundreds of
  kilometres from the observer.

HRDPS grid spacing does not imply equal spatial forecast accuracy. A model can
represent a fog bank at approximately the right scale while placing its edge on
the wrong coastline or clearing it at the wrong time. GOES improves the current
cloud analysis but nighttime low cloud, fog, parallax, cloud overlap, and cloud
optical depth remain difficult.

The critical product question is:

> Is the apparent clearing at a reachable alternative location real, persistent,
> and sufficiently better than remaining at the current site?

The research does not yet establish that available sources answer this with
enough skill to justify travel. See
[Cloud, fog, and astronomical line-of-sight forecasting](cloud-fog-line-of-sight.md)
and the [paid-provider forecast bake-off](paid-environmental-apis.md#required-forecast-bake-off).

### Evidence required

- Archived forecasts by initialization time, member, lead, and model version.
- GOES cloud products and surface ceiling/visibility observations.
- Directional all-sky imagery at representative coastal and inland sites.
- Evaluation by lead time, season, coast/inland class, cloud layer, and
  event-viewing elevation.
- Direct comparison of stay-versus-move rankings, not only point forecast
  error.

### Decision gate

Do not invest heavily in a generalized optimizer until the open-source baseline
demonstrates useful out-of-sample site-ranking skill over realistic travel
distances and observation windows.

## 2. Ground-truth quality and selection bias

Forecast data are plentiful; defensible optical outcome labels are not.

Common label errors include:

- treating no user report as a negative observation;
- treating a cloudy or offline camera as evidence of no aurora;
- applying an airport ceiling to a distant coastal site;
- interpreting satellite clear-sky classification as a clear oblique ray;
- treating camera-visible aurora as naked-eye-visible aurora;
- ignoring exposure, lens, gain, Moon glare, twilight, and horizon obstruction;
- collecting reports primarily during well-publicized geomagnetic storms.

Without attempted observations and valid negatives, Astraeus cannot calibrate
a probability of successful observation. It may not even be able to evaluate
ranking skill without substantial representativeness bias.

See [Scientific validation and calibration](scientific-design.md#validation-and-calibration)
and [Historical visibility labels](historical-celestial-events.md#joining-celestial-events-to-historical-weather).

### Evidence required

For each attempted observation:

```text
observer/camera operating state
exact location and interval
naked-eye versus camera outcome
equipment and exposure metadata
directional horizon clearance
cloud/fog/precipitation state
Moon and twilight state
positive, clear attempted negative, or unobservable label
```

An unobservable period must remain unknown for event visibility rather than be
converted to a negative.

## 3. Aurora apparent visibility

OVATION predicts auroral precipitation or intensity aloft. It does not directly
predict perceived brightness through a long atmospheric path from Atlantic
Canada.

Major uncertainties include:

- auroral emission altitude and vertical distribution;
- how far an auroral volume is visible equatorward of its footprint;
- substorm arcs and mesoscale structure smoothed by global products;
- the relationship between predicted precipitation and optical radiance;
- naked-eye contrast thresholds versus camera sensitivity;
- colour response and the effect of dark adaptation;
- confusion with haze, thin cloud, Moon glare, and light domes.

Kp, IMF Bz, hemispheric power, regional magnetic disturbance, and an OVATION
grid are activity evidence. None alone proves local optical visibility.

Until validation exists, output should separate:

```text
auroral activity confidence
local geometric opportunity
atmospheric visibility confidence
naked-eye or camera detectability confidence
```

Categorical language is safer than calibrated probability claims. See the
[aurora model review](sota-models.md#aurora-and-space-weather).

## 4. False precision and score design

A score such as 87 versus 82 implies more knowledge than an unvalidated
heuristic contains. Cloud, fog, transparency, darkness, Moon, terrain, light
pollution, and auroral activity are also dependent rather than interchangeable
independent factors.

A flat weighted average can allow excellent darkness to offset opaque cloud.
Blind multiplication can exaggerate poorly defined component functions.

Mitigations:

- enforce hard and near-hard gates;
- expose the limiting factor;
- calculate score and rank stability across ensembles and plausible inputs;
- show source disagreement and freshness;
- initially use broad opportunity bands in the user interface;
- retain numeric scores internally for ordering and evaluation;
- do not call the score a probability.

Suggested initial presentation:

```text
excellent opportunity
promising but fragile
marginal
poor
insufficient data
```

See [Hard constraints and soft quality](scientific-design.md#hard-constraints-and-soft-quality).

## 5. Historical forecast-vintage gaps

Reanalysis answers what the atmosphere most likely did after later observations
and consistent retrospective processing. It does not answer what Astraeus could
have predicted at issuance time.

Known risks include:

- ECCC operational forecasts are not all exposed through a convenient public
  historical bucket;
- exact historical OVATION grids are generally unavailable unless independently
  archived;
- mutable SWPC endpoints overwrite previous states;
- commercial `historical` APIs may return reanalysis or reconstructed weather;
- model versions, spacecraft inputs, and operational processing change;
- final OMNI and definitive geomagnetic indices contain information unavailable
  to an operational forecast.

The immediate mitigation is immutable, prospective archiving with raw bytes,
checksums, retrieval times, initialization times, lead times, members, source
versions, and quality metadata.

See [Historical environmental-data retrieval](historical-data-retrieval.md)
and [the OVATION archive gap](historical-celestial-events.md#the-ovation-archive-gap).

## 6. Obstructions, legal access, and safety

A park, protected-area, Crown-land, cadastral, or OpenStreetMap polygon does not
prove:

- nighttime entry is legal;
- a seasonal gate is open;
- parking is permitted or safe;
- the route avoids private or prohibited roads;
- the required directional horizon is clear of vegetation or structures;
- a site remains unchanged since the imagery or LiDAR acquisition;
- cellular service and emergency access are adequate.

False access recommendations create safety, legal, and reputational risk.

The first release should use curated, evidence-backed candidate sites and keep
unknown access or obstruction states explicit. Runtime closure and route checks
must be separate from static geographic preprocessing.

See [Observation-site obstructions and public access](site-obstructions-and-access.md).

## 7. Actionability and recommendation stability

A scientifically better site is not necessarily the better decision if the
clearing disappears before arrival or the improvement is too small to justify
travel.

The optimizer must account for:

- departure and setup time;
- forecast and nowcast publication delay;
- travel-time uncertainty;
- expected clearing persistence;
- score/rank stability under plausible scenarios;
- switching cost and recommendation churn;
- safe return travel;
- minimum material improvement over the current location.

The actual decision target should resemble:

```text
expected observation utility after travel and setup
- travel cost
- instability risk
- access/safety risk
```

not merely the highest atmospheric score at the destination.

## 8. Directional light pollution

VIIRS and Black Marble observe upward radiance, not the wavelength-dependent
sky brightness experienced along a particular astronomical ray. Directional
sector weighting is a useful heuristic but depends on distance, source
spectrum, aerosols, humidity, terrain shielding, atmospheric scattering, and
local lights below satellite resolution.

The uncertainty is most consequential when comparing sites with similar
weather and different nearby light domes. Local all-sky photometry or Sky
Quality Meter measurements are needed to validate the proxy.

## 9. Paid-provider incremental value

Meteomatics, Tomorrow.io, and other commercial providers offer normalization,
service guarantees, probabilistic fields, model selection, or proprietary
observations. Their feature lists do not establish superior Atlantic Canadian
cloud or marine-fog skill.

A paid provider should be adopted only after a blind, archived comparison
against the ECCC/GOES/observation baseline. Procurement must also establish:

- whether historical data are issued forecasts or reconstructions;
- permanent archival and derived-data rights;
- model, member, level, and initialization provenance;
- API redistribution, caching, and display rights;
- whether training or calibration on retained data is permitted.

See [Paid environmental APIs](paid-environmental-apis.md).

## 10. Product and behavioural risk

Astraeus's differentiation is synthesis and a decision, not an additional map
layer. That value proposition remains unvalidated.

Open product questions include:

- Will users trust a recommendation enough to travel?
- How much forecast improvement is worth a 20-, 40-, or 90-minute drive?
- Do users want one recommendation or evidence with manual control?
- How should the system communicate changing recommendations?
- Does an observation score improve decisions or create false certainty?
- Are enough relevant events available to create recurring engagement?
- Will users report attempted negatives and equipment details?

These questions require observation of real planning behaviour, not only survey
responses or App Store reviews.

## Largest current uncertainties

In descending order:

1. Site-ranking skill of HRDPS, REPS, GOES, and surface observations for
   Atlantic Canadian low cloud and fog at 0–6-hour lead times.
2. Whether full 3-D oblique-ray modelling materially improves decisions over
   simpler directional proxies when cloud geometry itself is uncertain.
3. Mapping OVATION and solar-wind inputs to apparent auroral brightness and
   elevation for naked-eye and camera observers.
4. Whether representative attempted-observation labels can be collected at
   sufficient scale.
5. Accuracy and freshness of open obstruction, gate, parking, ownership, and
   nighttime-access evidence.
6. Relationship between directional satellite radiance and actual local sky
   brightness.
7. Incremental Atlantic marine-fog skill of paid providers over the open stack.
8. Frequency with which moving locations changes an observation outcome enough
   to justify travel.
9. User interpretation of observation scores and uncertainty language.
10. Whether forecast errors are stable enough across season, geography, event
    direction, and lead time to support calibration.

## Areas of relatively high confidence

- Deterministic Sun, Moon, twilight, and eclipse geometry is tractable and
  reliable with pinned ephemerides and time inputs.
- The provider-oriented architecture is appropriate.
- ECCC, NOAA, GOES, Skyfield/JPL, terrain, and routing sources can support a
  functional vertical slice.
- Raw operational forecasts should be archived immediately.
- Curated destinations are safer than unrestricted geographic search for V1.
- An explainable observation score is appropriate before probability
  calibration.
- The open baseline should be measured before purchasing commercial providers.

These statements establish feasibility and sound architecture. They do not
establish that the optimizer will have useful forecast skill.

## Recommended feasibility experiment

Before the complete application, select approximately 20–50 representative
Atlantic Canadian sites across:

- exposed coasts;
- inland valleys;
- elevated terrain;
- urban and rural light environments;
- Nova Scotia, New Brunswick, Prince Edward Island, Newfoundland, and Labrador
  where observations permit.

Prospectively archive for at least a meaningful fog/cloud season:

```text
HRDPS and REPS forecast vintages
GOES cloud products
METAR/SPECI and ECCC SWOB
radar precipitation evidence
Sun/Moon/darkness geometry
directional all-sky imagery where possible
access and horizon metadata
issued Astraeus candidate rankings
Astrospheric issued forecasts where API terms permit archival
```

Evaluate:

- cloud-layer and fog reliability;
- clearing onset and duration error;
- directional usable-sky classification;
- rank correlation across candidate sites;
- top-choice success and regret relative to the best observed site;
- stay-versus-move decisions;
- naked-eye and camera outcomes separately;
- stability by lead time, season, region, and event elevation.
- point and stay/go/move skill relative to an experienced Astrospheric workflow.

### Go/no-go questions

1. Does the best-ranked site outperform the current location often enough to
   justify travel?
2. Is that improvement preserved after travel and setup time?
3. Can the system recognize when evidence is insufficient and recommend
   staying put?
4. Do directional and 3-D features outperform simpler point-cloud baselines?
5. Can uncertainty estimates distinguish stable from fragile recommendations?
6. Can outcomes be labelled without unacceptable selection bias?
7. Does Astraeus materially outperform manual comparison of reachable
   locations in Astrospheric, after accounting for travel and setup time?

If these questions cannot be answered positively, additional routing, scoring,
and interface sophistication will not rescue the core proposition.

## Review policy

Update this register when:

- a feasibility experiment produces new evidence;
- an upstream source, model, or licence changes;
- a risk becomes controlled by an implemented and tested mitigation;
- a new failure mode appears in field use;
- probability calibration begins.

Do not remove closed risks. Mark them controlled, record the evidence and date,
and retain the history of the decision.
