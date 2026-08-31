## ADDED Requirements

### Requirement: Observed and forecast Kp are separate and labelled by the provider
The planetary K index SHALL be stored and served as two series: the observed
series exactly as retrieved, and the forecast series carrying the provider's
own per-value status (`observed`, `estimated` or `predicted`) exactly as the
feed declares it. No forecast lead hours SHALL be synthesized for the Kp
outlook, no value SHALL move between the series, and a missing forecast feed
SHALL NOT stop the observed series from publishing or serving.

#### Scenario: Per-value status survives end to end
- **WHEN** the forecast feed marks a value `predicted`
- **THEN** the served series carries that value with status `predicted`, and
  no lead-hour is attached to it

#### Scenario: The forecast feed is down
- **WHEN** the forecast URL fails while the observed URL answers
- **THEN** the observed series is published and served, and the response
  states that no forecast series is available

### Requirement: Planetary quantities are never localized
The Kp and solar-wind series SHALL be stored with no horizontal coordinates
and SHALL never appear in point evidence: a planetary index carries no sample
distance, no sampled cell and no coordinate claim. Only the aurora
probability grid - a genuinely gridded product - SHALL be sampled at a
coordinate, as stored, in percent. The solar-wind source SHALL be described
as the SWPC real-time solar wind feed; no spacecraft SHALL be named unless
the feed's own source field declares it.

#### Scenario: Kp never wears a sample distance
- **WHEN** point evidence is built while Kp and solar-wind artifacts are
  published
- **THEN** no Kp or Bz field appears among the point fields

#### Scenario: Aurora probability is a real sample
- **WHEN** the aurora grid covers the requested coordinate
- **THEN** `/point` serves `aurora_probability` with the stored cell value,
  its provenance naming the OVATION product and the grid cell sampled

### Requirement: Space-weather serving fails closed on staleness and absence
`GET /space-weather` SHALL state, per feed, the record age against the
registry freshness threshold; a feed past its threshold SHALL be marked stale
with its age rather than served as current. An absent artifact SHALL be an
absent series with a notice, never a fabricated or carried-over value, and
fixture mode SHALL answer unavailable rather than inventing fixture indices.
The latest Bz SHALL be served with the instant it was measured; a gap in the
feed is a gap, never zero.

#### Scenario: A stale solar wind feed says so
- **WHEN** the newest stored Bz record is older than the registry threshold
- **THEN** the response marks the solar-wind series stale with its age and
  does not present the value as current

#### Scenario: Nothing is published
- **WHEN** no SWPC artifact is published
- **THEN** the response carries empty series with notices naming what is
  absent, and no value is invented

#### Scenario: Fixture mode
- **WHEN** the API runs in fixture mode
- **THEN** `/space-weather` answers unavailable stating that no fixture
  space weather exists

### Requirement: The aurora layer is a disclosed model nowcast
The aurora map layer SHALL be rendered only from the stored OVATION grid,
valid at the file's own forecast instant, with rendered-grid provenance
headers naming the source. Cells below the disclosed transparency threshold
SHALL be fully transparent, the colormap SHALL be identical day and night,
and the legend SHALL state: that the values are OVATION model probabilities
with a ~30-40 minute horizon, the transparency threshold, and NOAA's guidance
that at St. John's geomagnetic latitude (~53-54 N) aurora is typically
photographable from about Kp 4-5. A grid older than the staleness tolerance
SHALL make the layer unavailable with a notice, never rendered as current.

#### Scenario: Rendered with provenance
- **WHEN** the aurora raster is requested at a stored instant
- **THEN** the response carries `X-Weather-Image-Basis: rendered_grid`, the
  source id, the valid instant, and the colormap description

#### Scenario: Stale grid fails closed
- **WHEN** the newest stored grid is older than the staleness tolerance
- **THEN** the layer is not offered and the index carries a notice saying a
  feed gap is never rendered as absence of aurora

#### Scenario: The legend disclosure
- **WHEN** the aurora legend is requested
- **THEN** it names OVATION, the horizon, the transparency threshold and the
  Kp 4-5 St. John's guidance
