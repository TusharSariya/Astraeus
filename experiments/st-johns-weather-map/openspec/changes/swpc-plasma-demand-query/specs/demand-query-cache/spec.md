## ADDED Requirements

### Requirement: SWPC plasma uses one bounded current-document cache
The experiment SHALL retrieve only the canonical SWPC
`rtsw_wind_1m.json` document for an aware selected instant. Concurrent misses
SHALL coalesce into one request. The implementation SHALL enforce finite
transport, decoder and retained-entry bounds, record completion after the final
response byte and before decode, and SHALL NOT read a scheduled or retained
artifact as a fallback.

The decoder SHALL validate every row's time/source identity and all 29 known
native fields while retaining unknown future fields in the raw document
identity. It SHALL select the newest native minute at or before the selected
instant, strictly less than 900 seconds old. Exactly one active row SHALL be
preferred; otherwise the first feed-declared source label alphabetically SHALL
be used with a notice. Density, speed and temperature SHALL remain the nullable
values on that one row; an older minute or another spacecraft SHALL NOT fill a
gap.

#### Scenario: Fresh selected row
- **WHEN** a validated current document contains a native minute applicable to the selected instant
- **THEN** the response preserves that row's proton density in `cm-3`, speed in `km s-1`, temperature in `K`, measurement time, source label, active flag and overall quality
- **AND** it discloses canonical/effective URL, bounded safe headers, final-byte completion, byte count, digest and expiry

#### Scenario: Newest row contains gaps
- **WHEN** one or all three displayed plasma quantities are null on the newest applicable native row
- **THEN** those values remain null and no earlier minute or sibling spacecraft value is substituted

#### Scenario: Expired replacement fails
- **WHEN** the current document expires and replacement retrieval or validation fails
- **THEN** every plasma value is unavailable
- **AND** the response may disclose only the bounded cached acquisition and `values_withheld: true`
