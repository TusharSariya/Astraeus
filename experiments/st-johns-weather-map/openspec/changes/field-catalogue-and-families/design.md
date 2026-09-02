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
  six-hour mean (GEFS), five-layer fraction (GOES CCLF), observed dome cover
  (METAR oktas). Not comparable across definitions.
- Transparency: naked-eye limiting magnitude, magnitudes per air mass, ECCC
  class index. Not comparable across encodings. Column water vapour is Clear
  Sky Chart's encoding of transparency and is **not** a transparency field
  here: it is one quantity, and it is already `precipitable_water` in the
  humidity family. Two keys for one number would be the defect this change
  exists to remove, so the transparency family's note names the encoding and
  points at the humidity key rather than duplicating it.
- Seeing: ECCC class index, derived-here arcsecond estimate. Not comparable.
- Humidity: liquid versus mixed phase below freezing.
- Wind: u and v pairs versus speed only.

## How a profile field survives adapters that expand it per level

The level convention is one profile field with a level coordinate. GeoMet's
humidity profile already arrives that way. The GRIB adapters do not: they write
one two-dimensional variable per level (`relative_humidity_850hPa`), and
reshaping that is retrieval work this change explicitly excludes. So the
catalogue carries the one key with the coordinate, and each profile field also
declares a `level_suffix_pattern`; `registry.fields.resolve` turns a
level-expanded variable name into that one key plus the level it carried. The
catalogue's shape is the accepted one and no per-level key exists; the adapters
converge on the layout when a change owns their retrieval.

## Open questions carried into implementation

- Whether CF `standard_name` coverage is worth attaching for fields with no
  CF equivalent (class indices, health flags). Settled as implemented: the
  catalogue attaches `standard_name` where CF has one and leaves it null for
  class indices, flags, geometry and layered satellite fractions, rather than
  inventing names CF does not define.
- The exact split of GFS records into stored and `available-not-stored`.
  Partly settled: the family fields GFS stores today are enumerated in the
  catalogue's per-source mapping, and the records research verified outside
  them (`APCP`, surface `TMP`, `AOTK`, cloud-top pressure) are catalogued
  `available-not-stored` by name. The remaining bulk of the 1092 records is
  covered by the source's `family_fields_only` policy and its counted field
  total rather than record by record; enumerating 1092 `.idx` labels is a
  retrieval-time inventory, not a hand-written table.
- Whether a GeoMet coverage that appears upstream and is never requested can
  be seen at all. `uncatalogued_upstream_field` reports the coverages a run
  actually asked for; the unfiltered WCS capabilities document is 39 MB and
  the adapter deliberately never fetches it, so the "GeoMet advertises a new
  coverage" half of that scenario needs a capabilities enumeration this change
  does not own.
