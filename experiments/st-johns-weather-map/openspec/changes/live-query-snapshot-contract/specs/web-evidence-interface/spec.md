## MODIFIED Requirements

### Requirement: Each layer uses the latest earlier frame or declines
For the existing workbench, each active layer SHALL resolve the latest published
frame at or before the selected instant. It SHALL draw that frame only when its
age is strictly less than one hour. It SHALL never substitute a future frame.
With no qualifying frame it SHALL draw nothing and state the reason. Every drawn
layer SHALL display the actual frame time, run identity where known and age.
Provider-rendered imagery SHALL also verify its returned served time against
this rule rather than trusting the requested time.

This requirement supersedes nearest-frame and per-layer-tolerance selection for
the existing workbench. Separately accepted opt-in display interpolation remains
display-only and does not change `/point`, `/timeline`, feature or story reads.

#### Scenario: The closest frame is in the future
- **WHEN** the nearest frame is after the selected instant and an earlier frame is 20 minutes old
- **THEN** the earlier frame is drawn and the future frame is not requested as the answer

#### Scenario: The earlier frame is exactly one hour old
- **WHEN** the latest frame at or before the instant has age 3600 seconds
- **THEN** nothing is drawn because the selected limit is strictly less than one hour

### Requirement: The existing workbench uses one snapshot until explicit replacement
The current Map, timeline and point surfaces SHALL send one snapshot identity and
retain it across ordinary reads. Acquisition progress MAY be shown, but job
completion SHALL NOT replace visible evidence. An explicit refresh SHALL replace
all three surfaces atomically after their new responses agree on one snapshot.

#### Scenario: Acquisition completes during browsing
- **WHEN** a selection refresh job succeeds
- **THEN** the interface offers the new evidence and leaves the current labelled snapshot unchanged until explicit replacement
