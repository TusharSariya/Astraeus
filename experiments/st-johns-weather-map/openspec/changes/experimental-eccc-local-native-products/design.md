# Design

## Selected products

The partner stream is exactly `nl-water/{nlencl0001,nlencl0013,nlencl0015}` and `nl-firewx/{011,014,015}`. These are the six current partner stations inside the established Avalon evidence geography. DND/CCG's current partner directory lists British Columbia lighthouse identities; DFO moored-buoy stations were previously verified outside the evidence box. They are inventoried dispositions, not fetched product members. Existing normalized GeoMet SWOB and hydrometric products are outside this adapter.

The city stream is exact site `s0000280`, language `en`, selected from current and previous UTC hour directories. The issue identity comes only from the provider filename. MetNotes discovery accepts the official directory's truthful empty state and fetches no guessed payload.

## Bounds and validation

Partner admission covers six 256 KiB listings and six 128 KiB XML bodies: 2,359,296 received bytes, 786,432 artifact/filesystem bytes and 24,576 bytes of block margin. City admission covers two 256 KiB listings and one 128 KiB XML: 655,360 received bytes, 131,072 artifact/filesystem bytes and 4,096 bytes margin. Limits are hard refusal ceilings, not representative-size estimates.

XML rejects DTD/entity declarations, malformed documents, wrong roots, incomplete station sets and identity mismatches. Original bytes are the artifact, so upstream and artifact digests are identical. Each request records URL, bytes, digest, HTTP completion UTC and selected headers. A multi-station failure removes every staged partner artifact.

## Field disposition and owner gate

SWOB names fields through `element@name`; Citypage primarily names them by leaf tag and context. Provenance inventories every named or leaf element, native unit, attribute names, value/text presence and qualifier names. Values remain only in the immutable source body. No missing element/value becomes zero, no QA code becomes passed/failed, and no forecast condition/UV category becomes a canonical value.

A future contract must decide partner redistribution, exact SWOB QA-code meanings and canonical field mappings, Citypage forecast-period/revision/code semantics, and a native XML artifact/API route. Until then, structural acquisition cannot publish. The recommended follow-up is a native-document contract rather than forcing heterogeneous source fields into one generic numeric payload.
