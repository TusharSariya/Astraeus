## ADDED Requirements

### Requirement: GOES cloud-mask granules are ingested without invention
The GOES cloud-mask adapter SHALL discover and fetch the newest cloud-mask
granule (and its scan-paired cloud-top-height granule) from the provider's
public bucket over anonymous, polite HTTPS, and SHALL derive every geometric
quantity from the granule's own projection metadata — sub-satellite
longitude, perspective height and scan angles are read from the file, never
hard-coded. The granule SHALL be cropped to the experiment's context bounds
in fixed-grid index space, padded so parallax correction cannot move pixels
out of the window. Cloudy pixels with a valid cloud-top height SHALL be
parallax-corrected by the standard geometry (shifted toward the
sub-satellite point by height times the tangent of the viewing zenith, since
the apparent position is displaced away from it); cloudy pixels without a valid height SHALL keep their apparent
position and carry an explicit uncorrected flag. Values SHALL be regridded
by nearest neighbour onto a regular latitude/longitude grid whose cell is
never finer than the local native pixel footprint. Quality-flagged pixels
SHALL be preserved as an explicit invalid class, never dropped or converted
to missing. The published artifact SHALL carry the scan interval from the
granule's own time-coverage attributes, the product versions, quality
counts, and the regrid and parallax disclosure strings. When discovery finds
nothing new — including the normal case where the newest hour prefix is
still empty — the adapter SHALL fall back to the most recent complete scan;
when nothing within freshness exists it SHALL publish nothing and report the
gap rather than fabricating or republishing stale data as new.

#### Scenario: Geometry comes from the file
- **WHEN** a granule is processed
- **THEN** the projection used for cropping, zenith angles and parallax is
  built from that granule's own projection attributes, and a granule missing
  them is refused rather than assumed

#### Scenario: Quality flags survive to the artifact
- **WHEN** pixels carry bad-quality flags
- **THEN** the artifact stores them as the invalid class with their count in
  the attrs, and no flagged pixel becomes clear, cloudy or missing

#### Scenario: No new granule
- **WHEN** the listing shows no granule within the freshness threshold
- **THEN** no artifact is published, the outcome names the gap, and no prior
  artifact is re-stamped with a newer time

#### Scenario: A cloud with no height
- **WHEN** a cloudy pixel has no valid cloud-top height
- **THEN** it is published at its apparent position with the uncorrected
  flag set, not dropped and not shifted by a guessed height

#### Scenario: Resolution is never invented
- **WHEN** the regrid target is derived
- **THEN** its cell size is computed from the cropped granule's actual pixel
  spacing and is at least the local native footprint, and this is asserted
  by test
