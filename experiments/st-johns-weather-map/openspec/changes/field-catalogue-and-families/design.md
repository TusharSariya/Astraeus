# Design

## Why one quantity per key, and families on top

The glossary defines a field as one physical quantity at one level with one
unit and one declared phase. Two quantities under one key is the defect that
let HRDPS and GFS cloud share a colour ramp. Splitting keys fixes the data
path but would leave an activity profile asking for "cloud" with no name to
ask for. The family is that name: a group of fields measuring related but
non-identical quantities, carrying the comparability note. The decision layer
chooses members; the evidence layer never picks for it.

## Why phase is an attribute

Relative humidity over liquid and over mixed phase differ only below
freezing, by up to about 24 percent for identical air. Two keys would double
every humidity field for a difference that vanishes above zero. The phase is
already measured and stamped by `ingest/grib.py declare_rh_phase`; the
catalogue makes it a required attribute and adds the comparability rule that
flags a liquid-versus-mixed pair when either input is below 273.16 K.

## Why "every published field" and what it costs

The owner wants nothing dropped. For GeoMet sources server-side subsetting
makes this cheap: HRDPS at 377 coverages is about 5.5 GB resident and
dominates storage. For GFS, GEFS, ECMWF and ICON there is no server
subsetting, and the full-field probe measured about 1.7 TB per cycle for
everything everywhere. Ticket 20 therefore fetches only the catalogue-family
fields from those feeds and records the rest as `available-not-stored`: the
catalogue still knows the field exists, the reader can see it is not stored,
and nothing is hidden.

## Comparability rules the catalogue must carry from day one

- Cloud cover: opacity-weighted (HRDPS), geometric overlap (GFS, ECMWF),
  six-hour mean (GEFS), five-layer fraction (GOES CCLF). Not comparable
  across definitions.
- Transparency: column water vapour, naked-eye limiting magnitude, magnitudes
  per air mass, ECCC class index. Not comparable across encodings.
- Seeing: ECCC class index, derived-here arcsecond estimate. Not comparable.
- Humidity: liquid versus mixed phase below freezing.
- Wind: u and v pairs versus speed only.

## Open questions carried into implementation

- Whether CF `standard_name` coverage is worth attaching for fields with no
  CF equivalent (class indices, health flags).
- The exact split of GFS records into stored and `available-not-stored`.
