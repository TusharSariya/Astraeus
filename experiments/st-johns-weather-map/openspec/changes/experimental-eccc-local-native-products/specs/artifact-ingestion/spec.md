## ADDED Requirements

### Requirement: Experimental local XML acquisition preserves native truth without publication
The isolated experiment SHALL fetch only the six selected partner SWOB stations and St. John's English Citypage XML under declared complete-operation bounds. It SHALL preserve original bytes, request receipts, producer identity and times, and inventory every native named or leaf field plus structural elements carrying units, periods, languages, or codes. It SHALL preserve paths, attributes, units, missingness, and native codes without interpreting them. It SHALL NOT infer canonical values, QC verdicts, forecast periods or redistribution permission. Without an accepted manifest and delivery contract, every result SHALL remain incomplete, unregistered and nonpublishable.

#### Scenario: Partner omits a native value
- **WHEN** a named SWOB element is present without a `value` attribute
- **THEN** its inventory records `has_value: false` and no zero or carried value is created

#### Scenario: One selected station is unavailable
- **WHEN** any of the six required station listings or XML documents is absent, malformed, oversized or mismatched
- **THEN** the partner run is unavailable and no staged station artifact survives

#### Scenario: XML structure exceeds reviewed bounds
- **WHEN** a bounded XML body exceeds 4096 element nodes or depth 64
- **THEN** it is unavailable before recursive inventory and no partial artifact survives

#### Scenario: Artifact write fails after creating bytes
- **WHEN** either XML artifact write creates a partial file and then fails
- **THEN** the adapter removes the partial file and propagates the failure

#### Scenario: City page includes unmapped native fields
- **WHEN** the St. John's XML contains current conditions, forecast periods, warnings or UV elements without an accepted canonical contract
- **THEN** every leaf and every coded or unit-bearing structural element is inventoried and the immutable document remains nonpublishable

### Requirement: Empty MetNotes discovery does not invent a payload
The experiment SHALL treat an empty official MetNotes directory as observed unavailable with its retrieval time. If a JSON filename later appears, it SHALL refuse payload retrieval until complete size and structural bounds are reviewed.

#### Scenario: MetNotes directory is empty
- **WHEN** bounded discovery returns no documented MetNotes JSON filename
- **THEN** no payload request occurs and the result states observed empty rather than transport failure
