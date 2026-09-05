# Sky evidence and API handoff notes

Captured September 5, 2026 at 00:40 UTC from the running local API.
`sky-captures.json` preserves 22 requests with URL, capture time, HTTP status and
raw JSON. They are separate reads while the store may change, not an atomic
revision. Historical responses are not current conditions.

- `/timeline` and `/space-weather`: one request each.
- `/astronomy` and `/point`: five instants each at two coordinates.
- Signal Hill: 47.5704, -52.6816. Arbitrary point: 47.5615, -52.7126.
- Instants: September 4 at 00/01/06/12Z and September 5 at 00Z.
- All 22 requests returned HTTP 200. Astronomy answered live at all samples;
  point answered live at 00/01Z and unavailable at the later three samples.

## Observed limits

1. **Directional geometry:** astronomy returns Sun, Moon and core altitudes,
   lunar phase/illumination and intervals, but no azimuths. The site horizon
   cannot be applied or celestial positions placed directionally from this
   response. A production dome needs explicit azimuth/reference semantics and
   a decision about geometric versus horizon-adjusted events.
2. **Cloud geometry:** GFS low/middle/high fractions and geometric total are 0%
   at 00Z. At 01Z, low cloud and total are approximately 0.2%; middle and high
   remain 0%. Later layer fractions are null and total is not returned. The scalar point values
   do not establish directional cloud locations. Source definitions must remain
   separate; no scalar-to-dome cloud construction was added.
3. **Astronomy failure:** the current endpoint’s unavailable response schema
   uses numeric zero placeholders. The UI gates all astronomical values and
   windows on live mode plus provenance, rather than rendering those zeros.
   Nullable failure fields belong in the API-contract discussion.
4. **Provenance:** astronomy names DE442 and its explicit local derivation but
   omits `evidence_class`; the study maps this documented computation to the
   existing derived-here glyph and discloses the mapping in raw inspection.
   Space weather omits the class and full provenance; it is shown as class
   not supplied, not guessed to be retrieved from the product name.
5. **Freshness:** cloud retrieval is stale; run assessment is null with the
   contradictory reason “the adapter declared no run time” despite a supplied
   September 2 18Z run. Both fields remain visible. Space-weather feeds are stale.
   These are response-time assessments; the prototype does not relabel them current.
6. **Kp:** observed data ends September 2 at 21Z, so no observed point appears
   in the displayed September 4–5 window. The separate outlook includes nine
   points in that window; original statuses survive as circle/square/triangle
   marks. Points are not connected or moved between observed and outlook series.
7. **Solar wind:** latest Bz is -0.95 nT, Bt 6.66 nT at September 3 02:15Z.
   This is a timestamped global sample, not a value at the selected Focus time.
   Speed, density, Hp30 and Dst time series are not supplied by this response.
8. **Missing sky conditions:** no seeing/transparency class or local aurora
   probability was returned in these point samples. Null does not imply clear
   sky, favorable conditions or no aurora.
9. **Registry context:** `sky-registry.json` copies Signal Hill and NTV St. John’s
   Sky records. Signal Hill is hand-registered at 10° steps, approximately 1°
   precision, not field surveyed, terrain check not run. The camera is
   partnership-only with no position, orientation, geometry validation or
   permission to redistribute; no camera URL was fetched.
10. **Unrelated notice:** point/space responses contain an AWC TAF provenance
    rejection notice. It stays in raw responses; it is not presented as the
    cause of an unrelated absent field such as aurora probability.

## Existing owners

These observations inform [Settle the API contract additions the prototypes
proved](https://github.com/TusharSariya/Astraeus/issues/54). New astronomy
azimuth and unavailable-value semantics should be evaluated there with the
existing provenance, batching/revision and site/camera route gaps. No source
admission or registry promotion is authorized by this study.

The map’s camera placement and arbitrary-point fog remains pending the owner’s
Sky decision. Do not graduate or close it merely because the prototype displays
an absence. This study proves current limits; it does not select future behavior.
