## ADDED Requirements

### Requirement: Astronomical bands are drawn only from a served response
The interface SHALL render the darkness and moon timeline bands only from a
successful `/astronomy` response, positioned by the same window fraction
mapping as the coverage rows, and each band SHALL carry a text alternative
naming its intervals in words. When the astronomy response is unavailable,
the interface SHALL say the bands are unavailable with the reason; it SHALL
NOT render an empty band, which would read as "no darkness tonight". The core
window caption SHALL always carry the geometry-only wording served by the
API.

#### Scenario: Bands with text alternatives
- **WHEN** `/astronomy` answers with twilight bands and moon intervals
- **THEN** the darkness and moon rows render spans at the window fractions
  and expose text alternatives naming the interval times

#### Scenario: Unavailable is said, not drawn
- **WHEN** `/astronomy` is unavailable or unreachable
- **THEN** the band rows state unavailability and its reason, and no empty
  band is rendered
