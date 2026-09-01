## ADDED Requirements

### Requirement: Every offered interpolation method is derived from the same frames in the same cycle
The derivation SHALL compute every enabled interpolation method for every
cloud variable it derives, from that variable's own published frames, and
SHALL store each method's fields under a method axis of one artifact. Each
method's held-out skill SHALL be measured with that method's own
construction and published in the artifact's provenance beside the others.
A method that publishes a field no other method publishes SHALL leave the
others an explicit absent field rather than a ragged artifact.

#### Scenario: Two methods, one cycle
- **WHEN** two methods are enabled and a cycle derives a variable
- **THEN** both methods' fields are published in the same artifact and both
  are scored against the same held-out frames, so their scores are
  comparable

#### Scenario: An artifact from before the bench
- **WHEN** a published motion artifact carries no method axis
- **THEN** it is read as the single method it was derived by, and the map it
  serves keeps working

### Requirement: A method is scored by the construction it actually draws with
The held-out measurement SHALL evaluate the rule the client applies for the
method being scored, not the rule of any other method. It SHALL reconstruct
held-out frames at more than one fraction of an interval, and SHALL report a
structural measure beside the mean absolute error, because a construction
that dissolves harder is closer on average while being less like the
weather. The reversed-motion control SHALL remain the veto.

#### Scenario: A method whose composite differs from the baseline's
- **WHEN** a method mixes its two warps by a rule of its own
- **THEN** its published score is the error of that rule's reconstruction,
  not of the baseline's

#### Scenario: Right in the middle, wrong on the way there
- **WHEN** a construction reconstructs the midpoint well and the thirds
  badly
- **THEN** the published scores show it, because more than the midpoint is
  measured

#### Scenario: Winning by blurring
- **WHEN** a construction lowers its mean absolute error by dissolving more
- **THEN** its structural score falls at the same time, so the two together
  distinguish a smoother answer from a better one

### Requirement: A requested method is served exactly or refused by name
The motion endpoint SHALL serve the fields of the method a request names, and
SHALL name the served method back on the response. A method no registry
knows SHALL be refused as an invalid request. A known method the published
artifact does not carry SHALL be answered as absent, naming it, which the
client answers with the crossfade it already discloses. Neither SHALL be
answered with another method's fields.

#### Scenario: A method the artifact carries
- **WHEN** a request names a published method
- **THEN** that method's stored fields are served and the response names it

#### Scenario: A method this cycle did not derive
- **WHEN** a request names a registered method the artifact does not carry
- **THEN** the response is an absence naming that method, and the client
  crossfades and says so

#### Scenario: A method nobody registered
- **WHEN** a request names a method the registry does not know
- **THEN** the request is refused rather than answered with a substitute

### Requirement: A method may change how retrieved frames are shown, never what they contain
Every interpolation method SHALL be endpoint-exact: at each published
instant the real frame SHALL show untouched. A method that synthesises
displayed content rather than warping and mixing retrieved frames SHALL be
declared as such, SHALL be disabled by default, and SHALL NOT be offered
without an owner-approved carve-out that makes the on-screen disclosure say
the content was generated. A method whose output is only a displacement
field SHALL NOT require that carve-out.

#### Scenario: At a real frame
- **WHEN** the selected instant is a published frame instant
- **THEN** every method draws that frame exactly, with nothing mixed into it

#### Scenario: A generative method that has not been approved
- **WHEN** a method that synthesises pixels is registered
- **THEN** it is disabled and cannot be selected until the carve-out naming
  it exists
