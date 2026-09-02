## ADDED Requirements

### Requirement: A generated construction is named as GENERATED on the map
Whenever the drawn construction includes a generated display term, the
on-map disclosure SHALL say the word GENERATED, SHALL name the construction
and the options that produced it, SHALL say it is display only and gated on
a fixed control with its scores in the menu, and SHALL still name the real
frame times. A generative method SHALL be selectable only after an explicit
confirm, SHALL never be restored from a stored preference, and SHALL be
absent from the menu entirely when the server does not offer it. At a real
frame instant the disclosure SHALL say the retrieved frame is drawn
untouched.

#### Scenario: A generated term is drawn
- **WHEN** the reader has confirmed a generative method and the instant is
  between two frames
- **THEN** the disclosure contains GENERATED, the construction's name and
  its applied options, and the two real frame times

#### Scenario: The reader reloads
- **WHEN** a generative method was selected before a reload
- **THEN** the client returns to the default construction and the
  generative method is not selected again without a new confirm

#### Scenario: The server offers no generative method
- **WHEN** `/methods` carries no generative entry, or a notice that the kill
  switch is off
- **THEN** the menu shows no generated entry and, when present, shows the
  server's notice

### Requirement: A method that reduced to the default on a layer says so on the map
When the selected method draws the default construction on the current layer
- because a requirement is unmet, because every option was refused by the
gate, or because the served shader is the default's - the on-map disclosure
SHALL say the method reduced to the default on this layer and name the
reasons. The wording SHALL be keyed on the shader the server actually served,
never on the method the reader selected.

#### Scenario: A method the layer cannot use
- **WHEN** the selected method's requirement is unmet for the current layer,
  or every one of its options was refused
- **THEN** the disclosure names the method, says it reduced to the default
  construction on this layer, and lists the reasons

#### Scenario: The served shader disagrees with the selection
- **WHEN** the server names a shader other than the selected method's own
- **THEN** the disclosure describes the served shader's construction, not
  the selected method's

#### Scenario: The registry cannot be read
- **WHEN** `/methods` fails
- **THEN** the map draws the default construction, says the registry was
  unreadable, and makes no claim about whether a method reduced

## MODIFIED Requirements

### Requirement: The interpolation method is chosen from the server's own registry and named on the map
The client SHALL offer only the interpolation methods the server publishes,
with each method's measured skill shown beside it, and SHALL draw one method
at a time. The skill shown SHALL be the fixed-control skill - improvement
over a plain crossfade of the same frames - together with the sharpness
ratio, and the reversed-motion number SHALL NOT be shown. Each entry SHALL
carry the server-supplied plain sentence, gap sentence and expandable
science note, and the menu SHALL carry the server-supplied header line
stating that the producer treats hourly cloud timing as uncertain and that
everything offered is display between two real frames, never evidence.
Generative methods SHALL be listed apart, off by default, badged as
generating pixels, and never restored from storage. Whenever the drawn
method is not the default, the on-map disclosure SHALL name it, so what
produced the picture is never ambiguous. A method that has not been scored
SHALL be shown as unscored rather than as a zero score, and a registry that
could not be read SHALL leave the map on the default construction and say
so.

#### Scenario: Choosing a method
- **WHEN** the reader selects a published method
- **THEN** the map draws that method's fields and the disclosure names it

#### Scenario: The score beside a method
- **WHEN** a method's scores are shown
- **THEN** the line reads its improvement over a plain crossfade and its
  sharpness ratio against the real frame, and no reversed-motion number
  appears anywhere in the menu

#### Scenario: A method that has never met a real frame
- **WHEN** a registered method has no held-out score
- **THEN** the menu says it has not been scored, rather than showing zero
  skill

#### Scenario: The registry cannot be read
- **WHEN** the method list request fails
- **THEN** the map draws the default construction and the failure is stated
  rather than a method list being invented

#### Scenario: A remembered choice the server dropped
- **WHEN** a stored method is absent from the registry the server now
  publishes
- **THEN** the client returns to the default rather than requesting fields
  no cycle produces

#### Scenario: A remembered generative choice
- **WHEN** the stored method is a generative one the server still publishes
- **THEN** the client returns to the default and waits for a new confirm

#### Scenario: Copy the server did not supply
- **WHEN** an entry arrives without a plain sentence, gap sentence or note
- **THEN** the entry shows its identifier and says the copy is missing,
  rather than inventing a sentence
