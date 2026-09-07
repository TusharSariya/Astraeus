## MODIFIED Requirements

### Requirement: Layers are an additive stack with per-layer opacity and published draw order
The map SHALL support several layers drawn at once, each toggleable and each with its own opacity control. The reader SHALL be able to reorder the stack, and the current order, opacity, and visibility SHALL be represented in the URL. A reader with no saved or linked stack SHALL receive the five-layer Nowcast built-in selected in Wayfinder #46; a Saved stack loaded from the browser or URL SHALL replace the current stack explicitly. Every requested layer SHALL still resolve and fail independently, so an unavailable default member never becomes a substitute value or removes the remaining stack.

#### Scenario: Radar over a field
- **WHEN** two layers are enabled
- **THEN** both draw in the reader's current order, each at its own opacity

#### Scenario: A first visit
- **WHEN** no saved or linked stack exists
- **THEN** the Nowcast built-in requests its five declared layers and reports every unavailable member instead of filling it from another source or instant

#### Scenario: A linked stack is opened
- **WHEN** the URL names an ordered stack
- **THEN** it replaces the current stack without merging hidden defaults into it

#### Scenario: No layer selected
- **WHEN** the reader explicitly removes every layer from the stack
- **THEN** the text alternative states "Basemap only. No meteorological layer is requested." and the empty stack persists for that link

#### Scenario: No layer published
- **WHEN** `/layers` returns nothing or could not be read
- **THEN** the selector shows a status message naming the reason, the map remains a basemap, and no layer is invented
