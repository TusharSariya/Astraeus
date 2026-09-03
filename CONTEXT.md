# Astraeus

Evidence-first weather, sky and space-weather decision support for St. John's,
the Avalon Peninsula and, later, all of Newfoundland. The evidence layer holds
only what was retrieved or derived with provenance; a separate decision layer
scores activities over it.

## Language

### Evidence

**Source**:
A registry record for one producer product that this deployment can retrieve,
with its licence, cadence, endpoint and registry state.
_Avoid_: feed, provider (a provider owns many sources), dataset

**Product**:
What a producer publishes under one name, such as HRDPS or GOES-19 ABI cloud
mask. One product may become several sources.

**Field**:
One physical quantity at one level with one unit and one declared phase, such
as relative humidity over liquid water at 850 hPa.
_Avoid_: variable, parameter, band

**Field family**:
A named group of fields that measure related but non-identical quantities,
such as cloud cover, carrying the note on which members are comparable.
Activity profiles refer to families; the decision layer chooses members.

**Field catalogue**:
The canonical list of fields the evidence layer exposes, independent of which
source produced them. Every source maps its native quantities onto it.

**Artifact**:
An immutable, atomically published store of one source's retrieval for one run
or observation time, with manifest and provenance.

**Frame**:
One time instant of one layer, drawn from one artifact.

**Evidence class**:
How a value came to exist. One of: retrieved (this deployment fetched it as
the producer issued it), reprocessed (an intermediary transformed it before
delivery, declared with producer and intermediary named), derived-here (this
deployment computed it from retrieved inputs by a cited method, inputs listed,
allowed on data paths), intermediary-derived (an intermediary computed it from the producer's
retrieved fields by the intermediary's own method, which is named where
documented; never the display primary, never a derivation input),
generated-display (a display-only interpolation between
retrieved frames, never on a data path), uncalibrated observation (a citizen
or personal instrument, never used for verification).
_Avoid_: consensus, blend, estimate (say which class)

**Derivation method**:
An owner-approved, registered construction (name, version, citation, inputs,
physical range) that produces derived-here values from retrieved inputs.
_Avoid_: model, algorithm, post-processing

**Evidence box**:
The geographic extent every gridded source is subset to on ingest: 45.0 to
50.5 N, 58.0 to 46.0 W. The Avalon detail box (46.6 to 48.2 N, 54.3 to 52.4 W)
is where high-cadence products and validation apply first.

**Horizon tier**:
One of two forecast ranges served: the core window (3 h back to 24 h ahead at
full fidelity) and the planning window (to 14 days ahead from global products).

**Registry state**:
The ceiling a source may reach: operational, implemented-unverified,
catalogued, credential-required, licence-blocked, link-only, partnership-only,
unavailable, rejected, superseded. A live retrieval never promotes a state.
The state this glossary once called credential-blocked is written
`credential-required` in the registry, because the name should say the source
is admitted and waiting on a key, not that it was refused.

### Activities

**Activity profile**:
A named set of fields, thresholds, weights and time windows that the decision
layer scores. Running, astronomy, aurora and landscape photography are the
first four; new activities are new profiles, not new code paths.
_Avoid_: use case, mode, card

**Decision layer**:
The component that scores activity profiles over the evidence layer. Its
outputs are derived-here evidence and are never presented as producer output.
_Avoid_: forecasting model, blend

**Site**:
A registered preferred location with position, elevation and a hand-registered
directional horizon. A convenience, not a limit: every field is served at any
point in the evidence box.
_Avoid_: spot, location, station (a station is an instrument)

**Camera geometry**:
The registered position, bearing, field of view and horizon landmarks of a
camera, which make its frames usable as an input to cloud and fog derivation.
