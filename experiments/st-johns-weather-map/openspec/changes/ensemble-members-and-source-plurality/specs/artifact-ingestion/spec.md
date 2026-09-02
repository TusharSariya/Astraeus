## ADDED Requirements

### Requirement: An ensemble artifact carries its members and reports what arrived
Where a provider publishes individual members, the artifact SHALL carry them
as members rather than as a single field, and SHALL record which members
arrived against the count the registry declares. A run that retrieved fewer
members than declared SHALL publish as partial with the missing members named,
never as complete. Member completeness SHALL be computed from what was
decoded, never asserted from the request that was issued. A run that retrieved
no members SHALL NOT publish, because an ensemble artifact with no members is
not a thin ensemble but an absent one.

#### Scenario: Every member arrives
- **WHEN** all declared members decode for a run
- **THEN** the artifact publishes complete, and provenance records the member
  count and which member is the control

#### Scenario: Some members are missing
- **WHEN** fewer members decode than the registry declares
- **THEN** the run publishes partial, provenance names the missing members,
  and the shortfall lowers the verdict rather than being rounded away

#### Scenario: No members decode
- **WHEN** no member decodes for a run
- **THEN** nothing is published and the previous revision stays visible, as
  for any other incomplete run

### Requirement: A provider's own ensemble statistic is stored as retrieved
Where a provider publishes a statistic over its own members - a mean, a
spread, a percentile, a threshold probability - that statistic SHALL be stored
as a retrieved field of that provider, with the provider named and the
statistic named in provenance. It SHALL NOT be recomputed here from members,
and a statistic from one provider SHALL NOT be combined with members or a
statistic from another, because a mean over one member set and a mean over
another are not the same quantity. Where a provider publishes a statistic and
no members, the artifact SHALL NOT present the statistic as though it were a
member or a deterministic field.

#### Scenario: A provider mean is ingested
- **WHEN** an ensemble mean published by the provider is retrieved
- **THEN** it is stored as that provider's own field, provenance names it as
  the provider's mean over the provider's members, and nothing recomputes it

#### Scenario: A statistic is requested that the provider does not publish
- **WHEN** a spread is wanted from a source that publishes only members
- **THEN** the field is absent with a reason naming what the provider
  publishes, rather than being computed here from the members

#### Scenario: Two providers' ensembles are both present
- **WHEN** a member-publishing ensemble and a reduction-publishing ensemble
  are both current
- **THEN** each is stored under its own source, no statistic spans both, and
  neither is presented as a continuation of the other
