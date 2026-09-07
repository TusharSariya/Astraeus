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

### Requirement: All views use the selected Hyperlegible design system
The desktop SHALL use the #41 variant C canonical tokens: Atkinson Hyperlegible
Next and Mono, neutral greys, 15px base and 44px controls, with light, dark and
red-on-black night themes. Source slots SHALL remain stable by provider with
model line styles, and state/evidence shape and text SHALL remain meaningful
without colour. The selected red night tokens supersede the older Activity
ember treatment. Reduced motion SHALL suppress optional motion.

#### Scenario: A view switches to red night
- **WHEN** the reader changes theme while inspecting a source
- **THEN** Focus and inspector selection remain unchanged and evidence classes
  and verdict states remain identifiable through shape and text

### Requirement: The desktop shell is one Bench around a shared Focus
The interface SHALL present vertical controls for Map, Series, Sky, Activity, and Sources, one active view on the main stage, and at most one different view docked at the right. The Focus SHALL contain one site or arbitrary point and one exact instant shared by every open view. A view MAY enter full screen, and Escape SHALL return it to the Bench without changing the Focus.

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
The shell SHALL keep a full-width data-mode banner immediately below the Focus bar and the shared timeline at the bottom of the Bench. The banner SHALL name the data mode and summarize retrieved, stale, aged-out, and notice states without replacing or displacing the active stage. The Map SHALL keep a single-line disclosure strip on its bottom edge naming the number of layers drawn, generated-display use, and exceptions; complete details SHALL be reachable from that strip.

#### Scenario: Evidence is unavailable
- **WHEN** the API cannot supply current evidence
- **THEN** the banner states unavailable, the active stage remains on screen, and no fixture or previous live value appears in its place

#### Scenario: Some Map layers are absent
- **WHEN** only three of five requested layers have drawable frames
- **THEN** the strip states "3 of 5" and names or provides the bounded exception summary while the detail control exposes every layer's reason

### Requirement: The Map legend is the ordered evidence stack
The Map SHALL list the active stack top-first and grouped by field family. Every row SHALL expose an evidence-class glyph, source tag, short layer name, served run or observation identity when supplied, the frame actually drawn and its age, visibility, opacity, reorder controls, a provenance action, and removal. Legends SHALL appear once per family. The interface SHALL derive vocabulary only by an explicit existing client rule when the API omits it and SHALL disclose unknown identity rather than infer unsupported provenance.

#### Scenario: Two layers share a family
- **WHEN** two cloud layers use different provider legends
- **THEN** the family legend area shows both scales and states that they are separate

#### Scenario: Layer identity is absent
- **WHEN** a layer response omits an evidence class or source identity and no existing explicit mapping applies
- **THEN** its row says that identity is unknown and does not assume retrieved or a source

### Requirement: Every listed value uses the shared provenance ledger and inspector
Every listed evidence value SHALL have a permanent evidence-class SVG glyph in a fixed gutter and a visible source tag. Activating the value's specifically named provenance control SHALL select the row and fill one nonmodal docked inspector with the full provenance sentence, class, source and delivery kind, absence, method and inputs, quality, freshness, sample, comparability, terms, and capture identity that the response actually supplied. Missing properties SHALL be named as missing; the client SHALL NOT manufacture them.

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
