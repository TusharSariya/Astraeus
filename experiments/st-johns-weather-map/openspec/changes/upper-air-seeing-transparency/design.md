## Design

### D1 - Selection stays exact-pair, instantaneous-only

The five new messages join `GFS_IDX_SELECTORS` as exact (parameter,
lowercased level) pairs - `("UGRD", "200 mb")`, `("VGRD", "200 mb")`,
`("UGRD", "300 mb")`, `("VGRD", "300 mb")`,
`("PWAT", "entire atmosphere (considered as a single layer)")` - because
param-only matching is exactly the accident this adapter already fixed once
(GFS publishes UGRD at every isobaric level). The
`_INSTANTANEOUS_FORECAST` filter applies unchanged. `select_gfs_ranges`
returns the set of selected (param, level) pairs (not bare params) so the
decode loop can distinguish per-level inventory absence.

### D2 - Decode keyed on (shortName, cfgrib filter), levels split flat

The isobaric `u`/`v` shortNames are distinct from `10u`/`10v`, but one
cfgrib open per bare shortName cannot carry both 200 and 300 mb into the
flat dataset. The decode table becomes a tuple of specs: (shortName, extra
`filter_by_keys`, the idx pairs that justify the open, and a mapper from the
decoded variable to canonical names). The isobaric spec opens with
`typeOfLevel=isobaricInhPa`, then splits the `isobaricInhPa` dimension by
level into `wind_u_200hPa` / `wind_u_300hPa` (and v), so the published
dataset stays flat - deliberately: `/point` sampling skips pressure-dim
datasets when no pressure is requested, and these fields must reach `/point`.

### D3 - Two artifacts, one validation

All decoded fields are validated together against the run manifest (new
fields `optional=True`), then split at write time: `precipitable_water` joins
the existing `surface` zarr (it is a column total, sampled beside the other
surface evidence); the four wind components form a new `upper_air` zarr under
the same source. The profile-style pressure-dim artifact (radiosonde
precedent) is explicitly not used here - it would be invisible to `/point`.

### D4 - Byte ceiling is re-measured, not assumed

Five extra 0.25 deg messages at scattered offsets widen the gap-merged span.
The live smoke test asserts the new merged span against `MAX_BYTES_PER_LEAD`
with real inventory offsets; the ceiling is only ever raised with a measured
number in the comment, per the existing house comment on that constant.

### D5 - Serving: raw values and one disclosed derivation, no seeing index

`precipitable_water` is a stored provider value, served as stored. The wind
components are derivation inputs (added to `DERIVATION_INPUTS`), and the
u/v-to-speed/direction MetPy derivation already disclosed for 10 m wind is
generalized to a table of (u-var, v-var, speed-field, direction-field) pairs,
emitting level-suffixed fields with the same derivation and version strings.
Vertical level is carried in provenance (`vertical_level`). No seeing verdict
of any kind is computed; interpretation lives in web caption text.
