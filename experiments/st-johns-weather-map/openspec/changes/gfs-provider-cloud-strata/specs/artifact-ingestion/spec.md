## ADDED Requirements

### Requirement: Byte-range subsetting fetches only declared messages
An adapter that subsets a GRIB file through its `.idx` sidecar SHALL select
messages by exact (parameter, level) pair, never by parameter name alone, and
SHALL exclude alternate step types it does not read (time-averaged duplicates,
accumulations whose semantics are not pinned). The per-lead byte ceiling SHALL
bound the merged range set, and a selection that exceeds it SHALL fail closed
for that lead rather than fetch more.

#### Scenario: A parameter also published at many levels
- **WHEN** the inventory carries TMP at `2 m above ground` and at dozens of
  isobaric levels
- **THEN** only the `2 m above ground` message is selected and the range set
  stays under the per-lead ceiling

#### Scenario: A time-averaged twin of an instantaneous field
- **WHEN** the inventory carries both `LCDC:low cloud layer:7 hour fcst` and
  `LCDC:low cloud layer:6-7 hour ave fcst`
- **THEN** only the instantaneous message is selected

### Requirement: Heterogeneous-level subsets decode per message
A subset file whose messages sit on incompatible level types SHALL be decoded
message by message, each variable's scalar level coordinates recorded into its
attributes, and the fields then assembled flat. A message that was fetched but
cannot be decoded SHALL be a decode error that lowers the run verdict; an
optional message the provider's inventory did not publish SHALL NOT be.

#### Scenario: 2 m and 10 m messages in one subset
- **WHEN** a subset carries `t2m` at `heightAboveGround = 2` and `u10` at
  `heightAboveGround = 10`
- **THEN** both decode, the assembled dataset raises no merge conflict, and
  each variable's attributes state the level it was read at

#### Scenario: A fetched message that will not decode
- **WHEN** a selected message downloads but cfgrib cannot read it
- **THEN** the run carries a decode-error flag and does not publish as
  complete
