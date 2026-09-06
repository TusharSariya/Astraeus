## ADDED Requirements

### Requirement: CYYT TAF is admitted before its payload-bearing discovery

The experimental `awc-taf` worker path SHALL reserve the full declared receive,
local physical allocation, immutable-store, and conservative filesystem
allowance before requesting the AWC response. It SHALL enforce a 65,536-byte
response and artifact ceiling, a 640 MiB child address-space ceiling, a maximum
of 32 complete forecast groups, the measured 4,096-byte filesystem geometry,
and a 73,728-byte simultaneous physical reservation: one 65,536-byte artifact
ceiling plus one 4,096-byte worker temporary-directory allocation and one
4,096-byte child private-workspace allocation. Atomic promotion SHALL move the
single output inode rather than allocate a second artifact.
Unknown or unsupported enforcement SHALL refuse before the request.

#### Scenario: Exact boundary is admitted
- **WHEN** the complete response and output equal their declared ceilings
- **THEN** the worker admits them without thinning any report or forecast group

#### Scenario: Oversize or unsupported response is refused
- **WHEN** the body, output, group count, identity, time, or cloud-layer shape exceeds its bound
- **THEN** the operation fails without publication and its private workspace is cleaned
