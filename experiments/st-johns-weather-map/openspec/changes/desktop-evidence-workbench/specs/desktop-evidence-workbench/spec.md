## Purpose

Define the desktop Bench that keeps one shared place and instant while presenting retrieved evidence through a Map stage, companion views, and one consistent provenance interaction.

## ADDED Requirements

### Requirement: Series implements the selected Overview and temporary Compare
Series SHALL provide separate time-aligned field tracks in Overview and a
temporary in-memory field/source workspace in Compare. Switching SHALL
preserve Focus, instant, selections and provenance. Only compatible quantities
MAY share an axis; incompatible units or meanings SHALL retain separate aligned
axes. Native timestamps, checked gaps, unqueried spans, observations, forecasts,
raw ensemble members and provider reductions SHALL retain their distinctions.
The workspace SHALL NOT be saved, shared, persisted or used to author scoring.

#### Scenario: Incompatible fields are compared
- **WHEN** the reader compares temperature and wind speed
- **THEN** their axes remain separate and aligned in time, and switching to
  Overview preserves the selected evidence and Focus

### Requirement: Sky uses the selected Horizon instrument
Sky SHALL lead with the registered site horizon and separate scalar cloud-layer
gauges, with geometry and sky evidence alongside. An arbitrary point SHALL NOT
borrow a horizon. Unsurveyed registration SHALL remain disclosed. Scalar cloud
fractions SHALL NOT locate clouds or establish seeing/transparency. Absent
azimuths SHALL NOT become directional celestial positions or horizon-adjusted
events. Observed Kp, outlook and planetary context SHALL remain distinct from
point aurora probability. Camera eligibility and unavailable evidence SHALL
remain visible without inventing images or geometry.

#### Scenario: An arbitrary point lacks directional evidence
- **WHEN** Sky opens for a point with no registered horizon or celestial azimuths
- **THEN** it preserves available scalar evidence and explicitly names the
  missing horizon and direction without drawing invented geometry

### Requirement: Activity uses the selected four-lane Operational stack
Activity SHALL present four fixed-order horizontal profile lanes with the
server-returned verdict, score or withholding reason, limiting criterion,
aligned strip, coverage, next geometric window and disclosure. One lane SHALL
expand inline with hard stops before graded criteria, provenance and its
built-in Saved stack action, while other lanes remain legible. Printed labels
and distinct shapes/fills SHALL carry verdict state independently of colour.
The client SHALL NOT compute a missing verdict, score, criterion or window.

#### Scenario: A verdict is unavailable
- **WHEN** the server cannot return a profile verdict
- **THEN** its lane identifies the absence without a manufactured score, and
  any available evidence retains its own provenance

### Requirement: Sources retains all three selected perspectives
Sources SHALL provide Ledger by default, Family finder and Coverage lanes.
Switching SHALL preserve filters, Focus and the inspected source. Declared
registry/field coverage SHALL remain distinct from successful retrieval and
coordinate/time availability. Layer frames, native samples and expired evidence
SHALL retain their own identities. Unknown evidence class and unmapped layers
SHALL remain inspectable without inferred success or a capture fallback.

#### Scenario: A declared source has no retrieved samples
- **WHEN** the reader switches from its Ledger entry to Coverage lanes
- **THEN** the source remains selected and its declaration does not become
  demonstrated temporal or location coverage

### Requirement: All views use the original ocean design system
The desktop SHALL use ocean/teal panels, cyan and amber accents, a serif
Avalon wordmark and compact technical labels. Light and red-on-black night
themes SHALL use compatible tokens across all five views. Source slots SHALL
remain stable by provider with model line styles. State and evidence shape
and text SHALL remain meaningful without colour. Reduced motion SHALL suppress
optional motion.

#### Scenario: A view switches to red night
- **WHEN** the reader changes theme while inspecting a source
- **THEN** Focus and inspector selection remain unchanged and evidence classes
  and verdict states remain identifiable through shape and text

### Requirement: The desktop shell is one Bench around a shared Focus
The interface SHALL present one View menu for Map, Series, Sky, Activity, and Sources, one active view on the main stage, and at most one different view docked at the right. The Focus SHALL contain one site or arbitrary point and one exact instant shared by every open view. A view MAY enter full screen, and Escape SHALL return it to the Bench without changing the Focus.

#### Scenario: Views share one instant
- **WHEN** the reader changes the instant while Map is staged and Series is docked
- **THEN** both views read the same new Focus instant and neither creates a second authoritative instant

#### Scenario: A second dock is requested
- **WHEN** one view is already docked and the reader docks another
- **THEN** the new dock replaces the old dock and the stage remains visible

### Requirement: Focus and Map stack state are linkable without freezing live now
The client SHALL encode `site` or `lat` and `lon`, `view`, optional `dock`, and the ordered Map stack with opacity and visibility in the URL. It SHALL encode `t` only for a fixed instant; a Focus set to live now SHALL omit `t` so reopening the link uses the current session reference. Theme SHALL remain a browser preference and SHALL NOT enter the URL. An arbitrary point SHALL identify the nearest registered site and distance without borrowing that site's horizon.

#### Scenario: A live-now link is reopened
- **WHEN** a URL without `t` is opened in a later session
- **THEN** the client fixes a new session reference and does not reuse the earlier session's clock

#### Scenario: An arbitrary point is shared
- **WHEN** the URL carries `lat` and `lon`
- **THEN** the Focus displays those coordinates, the nearest registered site and distance, and that the site's horizon is not borrowed

### Requirement: Global evidence state stays visible while the Map remains usable
The shell SHALL use one 56px desktop toolbar containing the compact wordmark, View menu with companion docking, location, instant, concise API state, Layers and settings. Location, time and status details SHALL open in popovers. Settings SHALL expose theme and existing evidence panels. Long labels SHALL truncate visually with their full text available. Semantic headings and focus-visible skip links SHALL remain. The shared timeline SHALL remain within 80px when collapsed, retaining selected time and unavailable coverage. Timeline details and weather story SHALL expand over the map without resizing it. With panels closed at 1280×800 and larger, the map SHALL fill the remaining stage and occupy at least 80% of the application viewport. View changes SHALL preserve location, instant, selections and map camera. The Map SHALL keep a single-line disclosure strip on its bottom edge naming the number of layers drawn, generated-display use, and exceptions; complete details SHALL be reachable from that strip.

#### Scenario: Evidence is unavailable
- **WHEN** the API cannot supply current evidence
- **THEN** the toolbar states unavailable, the active stage remains on screen, and no fixture or previous live value appears in its place

#### Scenario: Some Map layers are absent
- **WHEN** only three of five requested layers have drawable frames
- **THEN** the strip states "3 of 5" and names or provides the bounded exception summary while the detail control exposes every layer's reason

### Requirement: The Map legend is the ordered evidence stack
One 360px right Layers overlay SHALL be closed initially, with Active and Browse tabs. Both lists SHALL use 28px single-line rows with existing 13px typography, thin separators and compact headings. Browse SHALL flatten each declared map capability into a stable layer row and retain one source row for sources without map capabilities. Each row SHALL expose selection, a short scientifically distinct name, compact availability and a details button; full identity SHALL remain accessible through its name, hover and details. Point-only rows SHALL say Point; information-only rows SHALL show status. Search SHALL occupy one compact line, followed by Group by, Filters and conditional Clear. Permanent capability counts and descriptive paragraphs SHALL be removed. An ungrouped Browse list SHALL expose at least 14 full rows at 1280×800 with filters and details closed.

Clicking a map row SHALL toggle that exact layer's stack membership, including unavailable layers. Repeated group appearances SHALL share selection, including hidden selections. Additions SHALL retain existing defaults and append at the top of drawing order; retained entries SHALL preserve settings. Active SHALL list actual drawing order top-first; clicking its main row SHALL remove it, while a separate visibility control SHALL hide/show without removal. Removing an Active row SHALL focus the next row, then previous row, then list heading. Enter/Space SHALL invoke the primary action. Right-click, Shift+F10, Menu key and the trailing details button SHALL open identical details without toggling membership. Point-only and information-only primary actions SHALL open details.

Details SHALL occupy the shared overlay space and include full identity, evidence class, availability/failure reasons, supplied timestamps, provenance, supported point/Series actions and selected-layer visibility, opacity and reorder controls. Generated, unavailable, stale and unknown states SHALL remain explicit. No inline capability trees or technical field-key buttons SHALL appear in the main lists. Opening details SHALL preserve filters, expansion and scroll; Escape SHALL return focus to the originating row. Saved-stack loading/naming SHALL remain behind Stacks. Legends SHALL appear once per family. Layers, Evidence and provenance SHALL share one overlay space with preserved return context. Vocabulary SHALL use only explicit existing client rules; unknown identity SHALL not become inferred provenance.

#### Scenario: Dense rows toggle one identity
- **WHEN** a hidden selected map layer appears in two subject groups
- **THEN** both appearances show selected, either main action removes that identity, and right-click or keyboard details access never changes membership

#### Scenario: Details preserve the list context
- **WHEN** details are opened from a scrolled filtered group and dismissed with Escape
- **THEN** filters, expansion and scroll are preserved and focus returns to the originating row
- **AND** removing an Active row focuses its next visible neighbour, previous neighbour or list heading

Verification: `web/src/workbench/MapStack.test.tsx`, `discovery.test.tsx` and the dense-menu browser proof cover membership, keyboard/return context, selected controls, density, themes, desktop sizes and zoom. Existing saved-stack, URL and camera regressions remain required.

#### Scenario: Two layers share a family
- **WHEN** two cloud layers use different provider legends
- **THEN** the family legend area shows both scales and states that they are separate

#### Scenario: Layer identity is absent
- **WHEN** a layer response omits an evidence class or source identity and no existing explicit mapping applies
- **THEN** its row says that identity is unknown and does not assume retrieved or a source

### Requirement: Every listed value uses the shared provenance ledger and inspector
Every listed evidence value SHALL have a permanent evidence-class SVG glyph in a fixed gutter and a visible source tag. Activating the value's specifically named provenance control SHALL select the row and fill one nonmodal overlay inspector with the full provenance sentence, class, source and delivery kind, absence, method and inputs, quality, freshness, sample, comparability, terms, and capture identity that the response actually supplied. Missing properties SHALL be named as missing; the client SHALL NOT manufacture them.

#### Scenario: A null value is inspected
- **WHEN** a field value is null with a returned absence reason
- **THEN** the row shows a dash and the reason state, and the inspector says what was absent and displays only returned provenance

#### Scenario: Generated display is inspected
- **WHEN** the Map draws an admitted generated-display method
- **THEN** the dashed generated glyph and GENERATED label remain visible and the inspector names its method, version, real frame inputs, and capture identity

### Requirement: Evidence interactions preserve keyboard context
View, stack, value, disclosure, and inspector actions SHALL use native interactive elements with specific accessible names and visible focus. Opening the inspector SHALL move focus to its heading; Close or scoped Escape SHALL return focus to the actual opener when it remains present, or to the nearest visible logical fallback. Rerendering SHALL preserve focus on the same logical control when it remains available. The interface SHALL NOT intercept arrow keys, Escape, Enter, or Space from a native control for an unrelated global action. Dynamic status updates SHALL be concise and polite unless they prevent safe continuation.

#### Scenario: Inspector returns to its opener
- **WHEN** a keyboard user opens evidence details and closes them
- **THEN** focus returns to that evidence action if it remains visible

#### Scenario: Selected evidence rerenders
- **WHEN** a fixed-clock fixture update rerenders the selected row without removing it
- **THEN** focus remains on the same logical action and the inspector selection remains coherent

### Requirement: Canvas evidence has a semantic alternative
The Map and every graphical time or evidence view SHALL provide a semantic text or table alternative that names the selected Focus, every displayed value or layer, source, evidence class, time identity, and absence reason. Colour SHALL NOT be the sole indicator of evidence class, selection, quality, or absence.

#### Scenario: A Map layer is not drawn
- **WHEN** a layer has no drawable frame
- **THEN** the Map alternative names the layer, source when known, and the same not-drawn reason shown visually

#### Scenario: Evidence is read without colour
- **WHEN** class colours are indistinguishable
- **THEN** glyph shape or fill plus visible text still identifies the evidence class and state

### Requirement: The rebuild preserves usable response-backed capabilities during migration
The shell SHALL keep every currently usable response-backed panel or view reachable until its accepted replacement is implemented and verified. A new view with no implemented response-backed body SHALL state exactly what is unavailable and SHALL NOT present inert or fixture-only controls as usable live capability.

#### Scenario: A current panel has no redesigned replacement yet
- **WHEN** the new shell is enabled before that panel's replacement is complete
- **THEN** the reader can still reach the current panel and its existing evidence behavior

#### Scenario: A view capability is absent
- **WHEN** a selected view has no implemented response-backed content
- **THEN** its stage names the unavailable capability and offers no control that appears to request unsupported evidence

#### Scenario: Map-first desktop visual acceptance
- **WHEN** the application is exercised at 1280×800, 1440×900 and 1920×1080
- **THEN** actual browser captures cover closed/open panels, all themes and 200% zoom; no controls are clipped or obstructed and the page does not scroll unexpectedly
- **AND** browser verification covers search, stack editing/saving, focus return, all views, URL restoration, unchanged camera, loading, failures, unavailable layers and long labels


### Requirement: The compact timeline exposes transport and native frames
The desktop timeline SHALL expose previous/next native frame, backward/forward
fixed-minute step, play/pause, reverse, interval selection, selected date/time,
Now, range selection and Tracks without opening details. The interval SHALL be
1, 2, 4, 8, 15 or 30 minutes, initially 1. Playback SHALL advance one interval
per wall-clock second, looping inside the displayed range, with no background
catch-up. Manual selections and range changes SHALL pause playback. Fixed-minute
steps SHALL not snap; frame actions SHALL select exact native timestamps.
Drag scrubbing SHALL snap to the visible-frame union with interpolation off,
otherwise to one minute. The current interpolation and per-layer resolution
rules SHALL remain unchanged. These desktop rules replace the older 16/32 min/s
continuous transport and five-minute free scrub behavior.

#### Scenario: The owner chooses a two-minute interval
- **WHEN** the reader steps forward or plays for one second
- **THEN** selected time advances exactly two minutes even for an hourly layer; the layer's native frame and offset remain disclosed

#### Scenario: Manual interaction interrupts playback
- **WHEN** the reader drags, selects a marker, changes range or makes another manual time selection
- **THEN** playback pauses and does not resume automatically

### Requirement: Display ranges and layer tracks preserve exact shared time
The client SHALL offer Near term (-1h..+6h), Day (-6h..+24h) and Outlook
(-24h..+14d), relative to the fixed session reference, bounded by the API window.
Near term SHALL be the default unless a restored selection needs a larger range.
Range changes SHALL preserve selected time and camera. An offscreen selection
SHALL offer a return to a containing range; Play outside a range SHALL begin at
its directional boundary. Tracks SHALL expand over the map, initially closed,
with one row per active stack entry in drawing order; hidden entries SHALL be
labelled and excluded from combined navigation. Selected frame times, offsets,
run changes, cadence and stale/loading/unavailable states SHALL remain distinct.
The collapsed dock SHALL fit 80px at desktop sizes; at 200% zoom controls MAY
reflow taller for access. Bottom expansions and right overlays SHALL coordinate
so their controls do not obstruct one another. Escape SHALL close the current
panel and restore focus.

#### Scenario: Mixed resolutions and a restored outlook instant
- **WHEN** radar, satellite, hourly and six-hourly layers are active and the URL restores +7d
- **THEN** Outlook contains the exact instant, each row preserves native cadence and gaps, and map camera is unchanged

### Requirement: Every returned frame timestamp remains reachable
The compact axis SHALL show measured collision-free time labels, Now, date
changes and the +24h planning boundary where applicable. It SHALL combine
coincident native markers and cluster overlapping targets without losing any
returned timestamp. Each cluster SHALL open a chronological exact-time chooser.
Tracks SHALL include a searchable frame list. Hover and keyboard focus SHALL
expose exact local date/time, UTC and declared forecast initialization separately.
No acquisition time SHALL be invented or confused with forecast valid time.
Published availability SHALL not be described as retrieved imagery without a
matching draw receipt. Empty history, unknown axes and failed requests SHALL
remain explicit; history and forecast classification SHALL come from the layer,
not from which side of Now a timestamp falls on.

#### Scenario: Dense historical frames
- **WHEN** hundreds of frames overlap on Outlook
- **THEN** counted clusters and the frame list expose every exact timestamp, selectable with pointer or keyboard

#### Scenario: A request finishes after the playhead moves
- **WHEN** imagery for an older selection arrives late
- **THEN** it cannot replace newer selected evidence; any retained image is named at its actual time

### Requirement: Newfoundland discovery omits geographically inapplicable sources
Owner direction, 2026-09-08: omit sources that cannot cover Newfoundland; retain
paid, credentialed and agreement-gated sources. All UI catalogue and source-status
surfaces SHALL omit exact source identities with documented geographic exclusion.
Temporary failures, stale data, unknown coverage, missing adapters, payment,
credentials and agreements SHALL NOT establish geographic exclusion. The raw
registry and API audit SHALL retain the records. This is a presentation rule,
not source admission or evidence filtering.

#### Scenario: A Europe-only source is returned by the API
- **WHEN** the catalogue or source-status endpoint returns Open-Meteo pollen/ammonia
- **THEN** it is absent from Browse, Sources and their counts and filters
- **AND** global and access-restricted sources remain visible with their actual status

Verification: `web/src/regionalSources.test.ts` exercises both shared UI boundaries.

### Requirement: Superseded sources are hidden without deletion
Owner direction, 2026-09-08: dated sources that have been superseded SHALL be
hidden from all UI catalogue and source-status surfaces, including Browse and
Sources. The declared `superseded` registry state SHALL determine this rule;
old timestamps, historical coverage and transient staleness SHALL NOT. Registry
records and API audit history SHALL remain intact. Replacement sources and
paid, credentialed or agreement-gated entries SHALL remain visible unless they
independently meet an explicit geographic exclusion or supersession rule.

#### Scenario: A retired feed has a replacement
- **WHEN** the API returns superseded standalone RAQDPS-FireWork and its RAQDPS replacement
- **THEN** the UI hides standalone FireWork and retains RAQDPS
- **AND** the raw records remain intact and unrelated historical or stale feeds remain visible

Verification: `web/src/regionalSources.test.ts` tests catalogue, status and discovery
consumers, including a future superseded identity without a hardcoded source list.

### Requirement: Opted-in local WeatherNext configuration survives normal restart
The owner's local restart workflow SHALL preserve an explicitly pinned WeatherNext
configuration through `make down up`. A checkout-local ignored configuration SHALL
opt into the existing Compose mount and private token refresh after API startup.
Without that file, startup SHALL perform no Google authentication. Refresh failure
SHALL fail the command visibly. No automatic run rollover, ingestion schedule,
credential persistence in Git or source-admission change is authorized.

Verification: Compose configuration validation, Make dry runs with and without
the local pin, existing token-refresh helper and a normal local startup.
