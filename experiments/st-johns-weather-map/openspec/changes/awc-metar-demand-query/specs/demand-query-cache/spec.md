## ADDED Requirements

### Requirement: CYYT METAR requests preserve selected-time applicability
A CYYT METAR demand query SHALL canonicalize all selections in one UTC clock hour to one bounded provider request covering the preceding two hours at the hour ceiling. It SHALL validate every returned row against that native request window and select only the latest observation at or before the selected instant with age strictly less than one hour.

#### Scenario: A future SPECI shares the cached response
- **WHEN** a cached response contains both a past observation and a later observation in the same canonical request window
- **THEN** the past observation is selected and the future observation is retained for later selections but is not served early

#### Scenario: An observation is exactly one hour old
- **WHEN** the latest observation at or before the selected time has age one hour
- **THEN** the response is explicitly unavailable and no older or future observation is substituted

### Requirement: The METAR cache is bounded and source truthful
The cache SHALL retain at most 64 complete responses and 4 MiB of response bodies, enforce the existing 64 KiB body and 64-row limits before admission, and key coalescing, failures, and validators by the canonical AWC request. A 204 response SHALL mean no observation in the requested provider window. Expired content SHALL NOT be returned after revalidation failure.

#### Scenario: Adjacent selected minutes share a provider request
- **WHEN** two selections fall after the same UTC hour boundary and before the next one
- **THEN** they share one canonical two-hour request and one fresh cache fill while local selection uses each requested instant

### Requirement: METAR observations do not depend on retained artifacts
The default point response and explicitly selected forecast responses SHALL obtain current CYYT METAR evidence from the demand cache, preserve `awc-metar-speci`, observation time, units, native missingness, report identity, response digest, and transport completion, and SHALL NOT fall back to a retained METAR artifact. Scheduled METAR acquisition SHALL fail before discovery after the replacement path is verified.

#### Scenario: The artifact store is unavailable
- **WHEN** a validated METAR demand result exists and no forecast store is reachable
- **THEN** `/point` returns the METAR evidence with an evidence-only selection and states that no forecast model is available
