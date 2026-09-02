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

## Response contract

Fixed before sections 3 and 4 began, so the API and the web could be built
against it at the same time:

- every served field value gains `key` (its catalogue key, the plain key with
  `level` separate where the variable was level-expanded), `family` (the family
  name), `phase` (`"liquid"`, `"mixed"` or `null`; non-null only for humidity
  fields, from `catalogue.PHASE_ATTRIBUTE` on the value), and `storage`
  (`"stored"`, `"available-not-stored"`, `"not-published"`; `stored` for
  anything actually served);
- the `/point` response gains `comparability`: a list of
  `{ family, a, b, comparable, reason, detail }` objects, one per unordered
  pair of served members within a family, `reason` and `detail` null when
  comparable, from `catalogue.comparability()` with the phases and the served
  2 m air temperature for humidity pairs;
- `/catalog` source entries gain `fields`: a list of
  `{ key, family, storage, upstream, note }` from
  `catalogue.source_mapping(source_id)`, so the web can show
  `available-not-stored` and `not-published` per source;
- a variable whose name `catalogue.resolve()` cannot resolve is not served:
  `value: null`, `data_mode: "unavailable"`, flag `uncatalogued_field` in
  `quality.flags`, and a notice naming the variable and the artifact.

Three things the implementation had to settle within that contract, none of
which changes it:

- **`a` and `b` are catalogue keys, and a pair may name one key twice.** A
  served member is one served value, so HRDPS and RDPS opacity-weighted cloud
  are two members of one key; the pair is `("total_cloud_opacity",
  "total_cloud_opacity")` and answers `comparable: true`, which is what the
  `field-catalogue` scenario "Two comparable members" requires. Pairs are
  deduplicated on the unordered key pair, so N sources of one key still cost
  one entry rather than N(N-1)/2 identical ones.
- **`field` and `key` stay two strings.** The API has served `temperature` for
  the 2 m air temperature and `wind_speed` for the 10 m wind since before the
  catalogue existed, and the level sits on `provenance.vertical_level`;
  `CATALOGUE_KEY_BY_FIELD` in `api/weather_api/models.py` is the whole list.
  The four cloud keys are *not* aliased: each is served under its own name,
  because one name for three quantities is the defect this change removes.
- **A derived humidity carries the phase its method declares.**
  `relative_humidity_from_dewpoint_liquid` evaluates Bolton's saturation
  vapour pressure over liquid water explicitly, so the derived value is
  stamped `liquid` from the method's own declaration. That is the method
  speaking, not an assumption about the inputs, and it is the only phase in
  the response that does not come off an artifact's own attribute.

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
- Whether a dew point on pressure levels belongs in the catalogue. Found
  during section 3 and left open: the catalogue carries `dew_point_2m`,
  `_40m`, `_80m` and `_120m` and one humidity profile field, and no dew point
  with a pressure-level coordinate. The API's unavailable profile list and the
  development fixture profile therefore no longer serve a "dew point" at 850
  hPa - a fixture may not invent a key any more than an artifact may, and the
  alternative was claiming the 2 m key at a pressure level. The dew point is
  still what the fixture's relative humidity is derived from. Extending the
  catalogue is registry work this section does not own.
