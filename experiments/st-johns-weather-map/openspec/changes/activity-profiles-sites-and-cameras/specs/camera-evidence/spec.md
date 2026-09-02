## ADDED Requirements

### Requirement: A camera is usable only through a complete registration record
Every camera SHALL have a registration record carrying: the operator and a
terms record quoting the operator's own words on redistribution; the
retrieval endpoint and the measured cadence; position with elevation and
vertical datum; bearing; horizontal and vertical field of view; roll; horizon
landmarks, each with bearing, distance and pixel position; privacy mask
regions; and the date and person of registration. No Avalon operator
publishes position, bearing or field of view
(`docs/research/wayfinder/camera-inventory.md`, branch
`research/camera-inventory`), so every geometry is hand-registered. A camera
whose record is incomplete SHALL NOT be retrieved, SHALL NOT be served and
SHALL appear in the catalogue with the missing elements named.

#### Scenario: An incomplete record
- **WHEN** a camera record omits its field of view or its landmark set
- **THEN** registration fails naming the missing elements, the camera is not retrieved, and the catalogue shows it as unregistered with the reason

#### Scenario: No camera is registered
- **WHEN** the camera registry is empty
- **THEN** the camera catalogue is empty with a notice, no camera-derived field is served, and every camera-derived field is `null`

### Requirement: A geometry is accepted only when landmark reprojection and the terrain horizon both agree
A camera geometry SHALL be accepted only when both checks pass: reprojecting
every registered landmark through the declared geometry reproduces its
recorded pixel position within a declared tolerance, and the terrain horizon
computed from a digital elevation model matches the visible skyline within a
declared tolerance. Both checks SHALL run at registration and SHALL be re-run
when a `camera_moved` health flag is raised. A geometry that fails either
check SHALL be refused outright; there SHALL be no degraded or partial-credit
geometry.

#### Scenario: A camera whose geometry fails reprojection
- **WHEN** reprojected landmarks miss their recorded pixel positions beyond tolerance
- **THEN** the geometry is refused naming each landmark and its pixel error, the camera serves no derivation, every camera-derived field for it is `null` naming `geometry_failed`, and frames may still be served with their health flags

#### Scenario: The skyline disagrees with terrain
- **WHEN** reprojection passes but the DEM terrain horizon does not match the visible skyline within tolerance
- **THEN** the geometry is refused naming the disagreeing bearings, and the camera serves no derivation

#### Scenario: No terrain model or no landmarks
- **WHEN** the DEM or the landmark set is unavailable so a check cannot be run
- **THEN** the geometry is not accepted, the unrun check is named, and the camera serves no derivation until both checks have run

#### Scenario: A camera is repointed
- **WHEN** the `camera_moved` health flag is raised on a frame
- **THEN** the geometry is marked unvalidated, both checks are re-run, and derivations are suspended with the flag named until they pass

### Requirement: No camera is admitted without a licence or written permission
A camera SHALL NOT be admitted for retrieval, storage or derivation unless
its terms record shows a licence permitting automated retrieval and
redistribution, or written permission from the operator. A camera with a
courtesy notice, an absent licence statement or reserved rights SHALL be
catalogued with status `partnership-only`: it is listed with its terms
evidence, it is not retrieved, and every field it would supply is `blocked`
with reason `partnership`. The Coast Guard harbour cameras, the City of St.
John's road cameras and the NTV cameras SHALL be `partnership-only` on this
basis. Fort Amherst SHALL be recorded as the first outstanding permission
request.

#### Scenario: A courtesy-notice camera
- **WHEN** the Fort Amherst camera is catalogued
- **THEN** its status is `partnership-only`, its terms record quotes the operator's courtesy notice, it is not retrieved, its fields are `blocked` with reason `partnership`, and the outstanding permission request is named

#### Scenario: Retrieval is attempted for a partnership-only camera
- **WHEN** a refresh names a `partnership-only` camera
- **THEN** the request is refused naming the camera and its terms, and no frame is fetched or stored

#### Scenario: Terms cannot be retrieved
- **WHEN** an operator's terms page cannot be read at probe time
- **THEN** the terms record states that the terms are unresolved, the camera stays `partnership-only`, and unresolved terms are never read as permission

#### Scenario: Written permission arrives
- **WHEN** written permission is recorded for a camera
- **THEN** the permission document and date are recorded in the terms record and the camera may be admitted; admission still requires a passing geometry

### Requirement: Frames are stored as evidence with health flags under the general retention rule
For each retrieved frame the deployment SHALL store the image, the capture
time, the retrieval time and health flags for: stale or duplicate, blur,
darkness, exposure, obstruction, lens water or snow, and camera moved.
Retention SHALL follow the general retention rule and SHALL NOT be extended
for camera frames. Health flags SHALL be computed, never asserted. A frame
whose capture time cannot be established SHALL be flagged and SHALL NOT be
served as evidence about any instant.

#### Scenario: A frame with a failed health flag
- **WHEN** a frame carries a raised blur, obstruction or lens-water flag
- **THEN** the frame is served with the flag visible, every derivation that reads it is refused and returns `null` naming the flag, and the frame is not silently dropped

#### Scenario: A duplicate frame
- **WHEN** the retrieved image is byte-identical to the previous frame or its capture time has not advanced
- **THEN** it is flagged stale or duplicate, it is not counted as a new observation, and the previous capture time stands

#### Scenario: A frame ages out
- **WHEN** a frame passes outside the retention window
- **THEN** it is purged and requests for that instant return `aged_out`, distinct from `null` and from `blocked`

#### Scenario: No frame was retrieved
- **WHEN** no frame is available for a requested instant
- **THEN** the response is `null` with provenance naming the camera and the last successful retrieval, and no neighbouring frame is served as if it were the requested instant

### Requirement: Camera derivations are limited to four claims and numeric visibility is refused
The only claims a camera derivation MAY make are: a fog class and a
visibility class, each with a confidence; a visibility bound given as the
distance to the farthest visible registered landmark and the nearest
invisible registered landmark, with both landmarks named; a daytime cloud
fraction within the camera's registered sector; and the presence of a fog
bank on the horizon. A numeric visibility in metres from the image alone
SHALL be refused. A claim SHALL name the camera, the frame times, the
geometry version and every landmark it used. Where the landmarks needed for a
bound are absent or flagged, the bound SHALL be `null` naming them.

#### Scenario: A visibility bound is served
- **WHEN** the farthest visible and nearest invisible registered landmarks are identified in a frame
- **THEN** the bound is served as an interval naming both landmarks and their distances, with `evidence_class: derived_here`

#### Scenario: A numeric visibility is requested
- **WHEN** code or a caller asks for a visibility in metres derived from a camera image alone
- **THEN** the request is refused naming the rule, and no number is produced

#### Scenario: No landmark is visible
- **WHEN** every registered landmark is invisible in a frame
- **THEN** the bound is `null` naming the absent landmarks, and no bound is inferred from the horizon alone

### Requirement: Every camera method enters the derivation registry disabled until a 30-day METAR validation
Every camera derivation method SHALL be added to the derivation method
registry with `enabled: false`. A method SHALL be enabled only after a
validation record comparing its output against CYYT METAR visibility and
cloud over at least 30 days spanning day, night, fog, rain and snow, recorded
with the method entry and approved by the owner. Until a method is enabled,
only frames and health flags SHALL be served for that camera, and every
camera-derived field SHALL be `null` naming the disabled method. A validation
record that does not span all five conditions SHALL NOT enable a method.

#### Scenario: A disabled camera method is requested
- **WHEN** a camera fog class is requested before validation
- **THEN** the field is `null` naming the method and `awaiting_validation`, and the camera's frames and health flags are still served

#### Scenario: An incomplete validation record
- **WHEN** a validation record covers 30 days of fog and rain but no snow and no night
- **THEN** enabling is refused naming the missing conditions, and the method stays disabled

#### Scenario: CYYT METAR is unavailable for the validation window
- **WHEN** METAR visibility or cloud cannot be retrieved for part of the window
- **THEN** the validation record states the gap, the window is not counted as complete, and the method stays disabled

### Requirement: Standing privacy refusals on camera imagery
The deployment SHALL mask the registered privacy regions of every frame
before storage and before service. The deployment SHALL NOT perform face
recognition, licence plate recognition, person tracking or vessel tracking;
SHALL NOT infer military activity; SHALL NOT claim "black ice detected"; and
SHALL NOT make a camera-only safe-wave or safe-road claim. These refusals
SHALL hold regardless of a camera's licence, of a reader's request and of any
derivation being enabled. Where a privacy mask cannot be applied, the frame
SHALL NOT be stored or served.

#### Scenario: A refused claim is requested
- **WHEN** any of the refused claims is requested from a camera derivation
- **THEN** the request is refused naming the standing rule, and no such value is produced or stored

#### Scenario: A mask cannot be applied
- **WHEN** the privacy mask regions are missing or masking fails for a frame
- **THEN** the frame is discarded unstored, the failure is recorded, and the instant is served as `null` naming `privacy_mask_unavailable`

### Requirement: Night frames are flagged and no daytime derivation runs on them
A frame captured outside the daylight boundaries given by the registered
DE442 geometry fields SHALL carry a darkness flag. No daytime derivation,
including sector cloud fraction and the daytime fog and visibility classes,
SHALL run on a frame carrying that flag. Night cloud from the NTV sky-dome
camera by star-field visibility SHALL be registered now as a derivation
method with `enabled: false`, subject to the same validation gate. When the
geometry fields needed to decide darkness are absent, the frame SHALL be
flagged `darkness_unknown` and daytime derivations SHALL be refused on it.

#### Scenario: A derivation run on a night frame
- **WHEN** a sector cloud fraction is requested for a frame carrying the darkness flag
- **THEN** the field is `null` naming the darkness flag, no daytime derivation runs, and no substitute construction is used

#### Scenario: Darkness cannot be determined
- **WHEN** the geometry fields that set the daylight boundaries are absent
- **THEN** the frame carries `darkness_unknown`, daytime derivations are refused on it, and the frame is not assumed to be daylight

#### Scenario: The sky-dome night method is requested
- **WHEN** night cloud from the sky-dome camera is requested
- **THEN** the field is `null` naming the registered method and its disabled state, and the method's registry entry is visible with its pending validation
