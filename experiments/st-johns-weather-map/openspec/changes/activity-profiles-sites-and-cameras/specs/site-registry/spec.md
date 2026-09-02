## ADDED Requirements

### Requirement: A site is a registered entity with position, elevation and a directional horizon
The deployment SHALL keep a site registry. Each site record SHALL carry a
stable site id, a name, a position in latitude and longitude, an elevation in
metres with its vertical datum, a hand-registered directional horizon giving
a horizon elevation angle per bearing at a declared bearing resolution, and
the date and person of registration. Signal Hill, Cape Spear and Quidi Vidi
SHALL be registered first, with further Avalon sites added as records. A site
record missing any of these elements SHALL fail registry validation and SHALL
NOT be served.

#### Scenario: A registered site is served
- **WHEN** a registered site is requested
- **THEN** its id, name, position, elevation with datum, directional horizon and registration record are returned

#### Scenario: A site with no horizon
- **WHEN** a site record carries no directional horizon, or a horizon with gaps in its declared bearing coverage
- **THEN** registry validation fails naming the site and the missing bearings, the site is not served, and every derivation that requires a horizon at that site returns `null` naming `site_horizon_missing`

#### Scenario: The site registry is empty or unreadable
- **WHEN** the site registry cannot be read
- **THEN** the site list is empty with a notice naming the failure, and field service at arbitrary points is unaffected

### Requirement: The hand-registered horizon is checked against a terrain horizon and never replaced by it
A site's directional horizon SHALL be hand-registered, because no source
publishes horizon and obstruction data at the resolution this deployment
needs and because buildings, trees and harbour structures are absent from
terrain data. A terrain horizon computed from a digital elevation model SHALL
be used as a check on registration and SHALL be recorded with the site. A
registered horizon that sits below the terrain horizon at any bearing beyond
a declared tolerance SHALL fail validation, because the terrain cannot be
seen through. The terrain horizon SHALL NOT be substituted for a missing or
failed hand registration.

#### Scenario: A registration disagrees with terrain
- **WHEN** a registered horizon is below the DEM terrain horizon beyond the declared tolerance at any bearing
- **THEN** registration fails naming the bearings and both angles, and the site is not served

#### Scenario: No digital elevation model is available
- **WHEN** the terrain horizon cannot be computed for a site
- **THEN** the site record states the check was not run, the site is served with that disclosure, and the terrain horizon is not assumed to agree

### Requirement: Sites are preferred locations and never a limit on where evidence is served
The evidence layer SHALL serve every catalogue field at any point inside the
evidence box, whether or not that point is a registered site. A reader SHALL
be able to evaluate any profile at any such point. The site registry SHALL be
a convenience list of preferred locations and SHALL NOT act as an allowlist.
Travel choice, routing and site ranking are decision-layer concerns and SHALL
NOT be implemented here. Where a profile needs a horizon and the requested
point is not a registered site, the horizon-dependent field SHALL be `null`
naming `no_registered_horizon`, and every field that does not need a horizon
SHALL still be served.

#### Scenario: A profile is evaluated away from any site
- **WHEN** a reader evaluates the astronomy profile at an arbitrary point in the evidence box
- **THEN** every catalogue field the profile names is served under the output contract, and no request is refused for being off-site

#### Scenario: A horizon-dependent field away from a site
- **WHEN** a horizon-dependent field is requested at a point with no registered horizon
- **THEN** that field is `null` naming `no_registered_horizon`, the remaining fields are served, and no nearby site's horizon is borrowed

#### Scenario: A point outside the evidence box
- **WHEN** a point outside the evidence box is requested
- **THEN** the request is refused naming the box, and no value is extrapolated to it

### Requirement: Sector sampling along a bearing is a registered derived-here method over retrieved gridded fields
Sampling a gridded field along a bearing from a site SHALL be an entry in the
derivation method registry of class `derived_here`. Its entry SHALL declare
its name, version, citation, input catalogue fields, output field, physical
range and range rule, and its reduction rule over the sampled cells. Its
parameters SHALL be the origin position, the bearing, the sector width, the
maximum range and the elevation-angle band. It SHALL read only retrieved
gridded fields and SHALL refuse any input whose evidence class is not
`retrieved`. Its output quality SHALL be no better than its worst input. It
SHALL NOT combine the same catalogue field from more than one source.

#### Scenario: A sector sample is served
- **WHEN** cloud in the north sector is sampled from a registered site
- **THEN** the value carries `evidence_class: derived_here`, the entry name and version, the origin, bearing, width, range and every input source with its own provenance

#### Scenario: A non-retrieved input
- **WHEN** the only grid available for a sector sample is `reprocessed` or `intermediary_derived`
- **THEN** the sample is refused, the field is `null` naming the input class, and no sample is produced from it

#### Scenario: The bearing leaves the grid
- **WHEN** part of the requested sector falls outside the retrieved grid or over cells that are all missing
- **THEN** the sample is `null` naming the uncovered fraction, and it is not computed from the covered part alone unless the entry declares a minimum covered fraction the sample met

#### Scenario: Sector sampling is disabled
- **WHEN** the sector-sampling entry is disabled at any of the three kill-switch levels
- **THEN** every sector field is `null` with a notice naming the level, and no unsectored substitute value is served in its place
