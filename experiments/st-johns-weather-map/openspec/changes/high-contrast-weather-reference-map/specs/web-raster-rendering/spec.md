## MODIFIED Requirements

### Requirement: The legend SHALL be the provider's own or absent

The interface SHALL NOT synthesize a colour scale or recolour a provider raster.
A drawn field with no legend is uninterpretable, so the legend is fetched from
the same provider that rendered the image; if the provider serves none, the
layer is drawn without one and says so. Geographic coast, lake, road, boundary
and label layers MAY be drawn above the image only as reference information and
SHALL use a separate, non-value-encoding cartographic treatment.

#### Scenario: Legend accompanies an active raster layer
- **WHEN** a raster layer is active and reports `legend_available: true`
- **THEN** the provider's exact legend image is displayed adjacent to the map
- **AND** no colour scale is constructed and no raster pixel is recoloured in
  the client

#### Scenario: No legend is served
- **WHEN** a raster layer reports `legend_available: false`
- **THEN** the layer is drawn and explicitly noted as carrying no provider
  legend

#### Scenario: Reference geography crosses a raster
- **WHEN** coastline, lake, road, boundary or label geometry is visible above a
  provider raster
- **THEN** it is identified as cartographic reference, not part of the legend
- **AND** the provider raster remains unchanged below it
