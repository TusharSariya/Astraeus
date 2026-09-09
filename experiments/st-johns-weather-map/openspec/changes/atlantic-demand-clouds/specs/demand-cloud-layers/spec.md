# Atlantic demand clouds

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Owner authorization: implementation request dated 2026-09-08. Experiment only.
This amends selected-time delivery; existing stored layers and defaults remain.

## ADDED Requirements

### Requirement: Selected native cloud layers
The experiment SHALL offer noaa-goes19-demand-cloud-mask and
eccc-rdps-demand-total-cloud before acquisition, with loading and unavailable
states. Each SHALL cover only actual native coverage within west -70, south 40,
east -40, north 55, including water. Uncovered areas SHALL be disclosed without
extrapolation. Viewport and opacity changes SHALL reuse selected science data.
Failed replacements SHALL clear images and obsolete responses SHALL be ignored.

#### Scenario: Optional acquisition
- **WHEN** a user enables a layer and selects a time
- **THEN** only that selected native frame is acquired, with no scheduled or sequence downloads

#### Scenario: Map-only cloud mask controls
- **WHEN** GOES cloud mask is browsed or enabled
- **THEN** the interface identifies it as an on-demand map layer with its actual draw state
- **AND** it does not create an unsupported point reading or offer a data-only selection state

### Requirement: NOAA cloud classification delivery
GOES SHALL select the nearest actual nonfuture Full Disk ACMF scan within 300
seconds of selection. Archive inventory SHALL use bounded daily metadata pages
within the visible past week, without science downloads. The interface SHALL
show actual timestamps and offer Latest available scan when selection is a gap.
One ACMF and scan-paired ACHAF SHALL use anonymous HTTPS with 80/20 MiB ceilings,
a 2 GiB decoder, 90-second deadline and 16 MiB cropped output. The finite cache
SHALL hold at most four frames/64 MiB and coalesce duplicates. Existing quality,
nearest-neighbour regridding and parallax rules SHALL apply; absent valid height
SHALL retain explicitly uncorrected position. Existing five-state day/night
palette SHALL remain: transparent clear, white confidence classes and violet-grey
invalid. Alpha SHALL mean detection confidence, never amount or thickness.

#### Scenario: Gap and missing height
- **WHEN** no scan is within half cadence or height is unavailable
- **THEN** the scan gap remains unavailable, while a valid mask with missing height retains its labelled apparent position

### Requirement: Native RDPS white opacity
RDPS SHALL reuse the existing native coordinator for a cloud-only regional
request, retaining legacy point bounds and finite acquisition/cache limits.
Run/lead selection SHALL use advertised native times. Nearest rotated-grid-cell
sampling SHALL render valid cells white with alpha percentage/100 times layer
opacity, and missing cells distinctly from valid transparent zeroes. No WMS
colour inversion or inferred percentage SHALL be used. Metadata-only inventory
SHALL reuse native run discovery. New cloud acquisitions SHALL share at most two
concurrent slots and coalesce duplicate science requests.

#### Scenario: Native cloud and missingness
- **WHEN** 0, 50, 100 percent and missing values are rendered
- **THEN** valid RGB is white with the declared alpha, missing is distinct and sampled centres agree with the native point rule

### Requirement: Atlantic WN3 native rectangles
The source-grid API SHALL accept named avalon and atlantic regions, defaulting
to avalon. The app SHALL request atlantic. Native 0.1-degree intersecting
rectangles, axes, masks, clipping and region cache identities SHALL be preserved.
Each needed chunk SHALL be fetched once; point reuse SHALL match region, run,
time and field. Response and worker output SHALL be at most 2 MiB, with existing
upstream bounds and four-frame/8 MiB cache unchanged. Geometry SHALL be indexed
native rectangles; frame provenance SHALL be stored once and inspection details
SHALL be constructed only for the selected cell.

#### Scenario: Wider frame and compatibility
- **WHEN** Atlantic is requested
- **THEN** all approximately 45451 intersecting cells including boundary cells and water are retained
- **AND** omitted region still delivers the unchanged Avalon footprint

### Requirement: Available time inventory
Typed demand-layer inventory SHALL distinguish advertised times from downloaded
values, feed timeline markers, Tracks and previous/next navigation, and disclose
unavailable inventories. Selection SHALL fetch only its own science frame.

#### Scenario: Inventory discovery
- **WHEN** the timeline is browsed
- **THEN** native advertised times appear without downloading a forecast sequence or inventing future observations

#### Scenario: Scan timestamps remain discoverable beside forecasts
- **WHEN** GOES is enabled and the selected time has no observed scan
- **THEN** the compact timeline exposes a labelled selector of actual inventoried scan timestamps and a latest-scan action without requiring Tracks
- **AND** selection changes only on user action; listing scans does not acquire science frames
