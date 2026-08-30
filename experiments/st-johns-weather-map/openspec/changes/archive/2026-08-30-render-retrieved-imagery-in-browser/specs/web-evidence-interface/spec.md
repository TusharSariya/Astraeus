## ADDED Requirements

### Requirement: The interface SHALL disclose each layer's evidence basis

The interface SHALL state each layer's `evidence_basis` in words. Layers now reach the map by two different routes. A published artifact passed
ingestion, QC, manifest validation and atomic publication. A live-proxied layer
did not: it is fetched from the provider at request time and bypasses that spine
entirely. Both are genuinely retrieved, but they do not carry the same assurance,
and a reader cannot weigh what they are shown without being told which is which.
This disclosure is the condition under which the proxied route was permitted.

#### Scenario: A proxied forecast layer is labelled
- **WHEN** a layer reports `evidence_basis: "live_proxy"`
- **THEN** the interface states that it is live-proxied imagery and not a
  published artifact, in words, wherever that layer's state is shown
- **AND** the statement appears in the text alternative as well as the visual panel

#### Scenario: A published layer is not overclaimed
- **WHEN** a layer reports `evidence_basis: "published_artifact"` but its imagery
  is live-rendered
- **THEN** the interface does not describe the drawn image as a published artifact

#### Scenario: An absent or unrecognised basis fails closed
- **WHEN** a layer omits `evidence_basis` or declares an unrecognised value
- **THEN** the interface treats its basis as unknown and says so
- **AND** it does not assume the stronger of the two

### Requirement: A control SHALL NOT be permanently unreachable

The interface SHALL NOT render a control whose enabling condition the API can never satisfy. An affordance that can never be enabled is indistinguishable to the reader from
one that is merely disabled right now, and it misrepresents what the system can
do. Forecast model and product controls are gated on a source state the API
never emits by design, so every such control is permanently dead while
`/point?product=` is fully implemented.

#### Scenario: Product selection is reachable or absent
- **WHEN** the catalogue contains sources the API will accept as a product
- **THEN** those products are selectable
- **AND** no control remains rendered whose enabling condition the API cannot
  ever satisfy

#### Scenario: A genuinely unavailable option explains itself
- **WHEN** a product cannot be selected because of its own declared state
- **THEN** it is disabled with the reason drawn from the response, not from a
  predicate the API never satisfies

## MODIFIED Requirements

### Requirement: A control that cannot change the request is disabled and says why
A selector SHALL only offer options the API actually returned; an empty option list SHALL leave the control disabled with the reason stated. A field the API reports in provenance but has no request parameter for SHALL be presented read-only with an explanation, because a control that accepts a choice and then discards it misstates what was requested. Model and product controls SHALL be offered only for catalogue sources that `/point` accepts as a `product` value; registry `state` is a ceiling that never reads `active` and SHALL NOT gate them.

#### Scenario: Run, member and level
- **WHEN** the expert controls are shown
- **THEN** run, member and level are read-only readouts of what the response reported, explaining that the point request has no parameter for them

#### Scenario: A catalogue that could not be read
- **WHEN** `/catalog` failed
- **THEN** the provider and product selectors are disabled with the catalogue error stated, rather than showing an empty but operable control

#### Scenario: A product whose source is not selectable
- **WHEN** a catalogue source maps to no `/point` `product` token
- **THEN** no model button or product option is rendered for it, rather than a control that no response could ever enable

#### Scenario: A model offered while no source is active
- **WHEN** the catalogue lists a source `/point` accepts as a product and its registry state is anything other than `active`
- **THEN** its model button is enabled and selecting it sends the endpoint's own product token, not the catalogue's prose product name
