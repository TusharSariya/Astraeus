## ADDED Requirements

### Requirement: Imagery availability is separate from stored sample time
Layer responses used by the desktop SHALL distinguish stored sample/frame times
from declared imagery availability. Imagery availability SHALL state its known,
unknown or unavailable status, check time, published times or intervals where
known, and an explicit reason where unknown. It SHALL NOT infer continuous
coverage from a cadence or promise that a raster request will succeed. A served
raster SHALL continue to disclose the actual time and provenance of the image
returned.

#### Scenario: A provider declares no imagery availability
- **WHEN** the layer index cannot establish imagery availability
- **THEN** it reports unknown with a reason and does not manufacture image times
