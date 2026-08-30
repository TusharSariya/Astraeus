## Purpose
Define how GRIB2 is subset before download and normalized after decode, including the rotated and curvilinear grids HRDPS and RDPS publish on, so that a global file never exceeds the experiment's storage cap and a 2-D coordinate grid is never treated as a pair of sliceable axes.

## Requirements

### Requirement: Byte-range subsetting from the `.idx` sidecar precedes any decode
An adapter SHALL parse the provider's `.idx` sidecar, select only the messages it declared by parameter, level and forecast hour as an explicit allowlist, and collapse those messages into the fewest HTTP byte ranges. Message length SHALL be the gap to the next offset. A malformed sidecar SHALL raise rather than yield a guessed range.

#### Scenario: Adjacent messages
- **WHEN** selected messages are contiguous
- **THEN** they merge into one request, while separated messages stay separate unless a gap allowance permits merging

#### Scenario: A non-final selection is always bounded
- **WHEN** the selection does not include the last indexed message
- **THEN** no range is open-ended, because an open range would defeat subsetting

#### Scenario: The trailing open range is capped
- **WHEN** the final indexed message is selected and the sidecar states no file size
- **THEN** the open-ended range is bounded by a trailing cap, so a `bytes=N-` request cannot pull the remainder of a 521 MiB file; if the cap is too small the message is short and the decode fails loudly, which the adapter reports as a decode error rather than a silent gap

#### Scenario: A malformed sidecar line
- **WHEN** a line has too few fields, an unparseable offset, or non-increasing offsets
- **THEN** a `GribError` is raised rather than a range being guessed

#### Scenario: A missing run date
- **WHEN** the sidecar's date token is absent or unparseable
- **THEN** the run time stays `None` rather than being filled in

### Requirement: Rotated and curvilinear grids are recognised, not assumed away
HRDPS and RDPS publish on a rotated lat/lon grid, so the decoder returns `latitude` and `longitude` as 2-D fields over anonymous `y`/`x` dimensions. Code SHALL detect this shape explicitly and SHALL NOT assume 1-D sliceable axes. Selection by latitude/longitude label is invalid on such a dataset and SHALL NOT be attempted.

#### Scenario: A rotated grid is recognised
- **WHEN** latitude and longitude are 2-D over dimensions that are not themselves named latitude/longitude
- **THEN** the dataset is reported curvilinear, while a plain 1-D grid is not

#### Scenario: A rotated grid is cropped by index
- **WHEN** a curvilinear dataset is cropped to a bounding box
- **THEN** it is cropped to the smallest index window containing every cell inside the box — a superset of the box — rather than raising or being sliced by coordinate label

#### Scenario: The provider's own cells survive the crop
- **WHEN** a curvilinear dataset is cropped
- **THEN** the provider's cell values and their real coordinates are unchanged, because a rotated grid cannot be trimmed to a lat/lon rectangle without regridding and regridding would invent values

#### Scenario: A rectilinear grid is cropped by label
- **WHEN** a 1-D grid is cropped, in either ascending or descending latitude order
- **THEN** it is sliced by coordinate label with the slice direction matched to the axis order

#### Scenario: A 0-360 longitude axis
- **WHEN** the longitude axis exceeds 180
- **THEN** it is shifted onto -180..180 before the crop, and a 1-D axis is re-sorted afterwards while a 2-D grid is not, since it is cropped by index anyway

#### Scenario: A box outside the domain
- **WHEN** the crop matches no cells on either grid shape
- **THEN** a `GribError` is raised stating that the run does not cover the domain, rather than an empty grid being published

### Requirement: Units are normalized only where the conversion is known
Unit normalization SHALL convert only recognised units to the project's canonical set and SHALL leave anything unrecognised untouched, recording the provider's own units in provenance. Inventing a conversion is worse than surfacing the provider's units.

#### Scenario: A recognised conversion
- **WHEN** a variable carries kelvin, a 0-1 cloud fraction, or pascals on a pressure-named variable
- **THEN** it is converted to degC, percent or hPa respectively, with `original_units` recorded

#### Scenario: An unrecognised unit
- **WHEN** a variable carries a unit outside the recognised set
- **THEN** its values are passed through unchanged and its units are carried verbatim into provenance

#### Scenario: Normalization survives a rotated crop
- **WHEN** unit normalization runs on a curvilinear dataset after cropping
- **THEN** it behaves identically to the rectilinear case

### Requirement: An accumulation is never divided into a rate
A precipitation accumulation SHALL be tagged with its interval and its `time: sum` cell method, and SHALL NOT be converted to a rate. An accumulation over an interval is a different quantity from a rate, and converting between them silently invents information.

#### Scenario: Tagging an accumulation
- **WHEN** an accumulation variable is normalized with a positive interval
- **THEN** it carries the interval in hours, `cell_methods = "time: sum"` and semantics stating it is an accumulation and not a rate, with its values untouched

#### Scenario: A non-positive interval
- **WHEN** the stated accumulation interval is zero or negative
- **THEN** a `GribError` is raised
