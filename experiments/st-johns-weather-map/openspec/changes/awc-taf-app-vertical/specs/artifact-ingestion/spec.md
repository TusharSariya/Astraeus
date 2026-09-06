## ADDED Requirements

### Requirement: CYYT TAF preserves native forecast-group identity

The experimental `awc-taf` artifact SHALL retain the raw TAF, issue time,
overall validity, and every forecast group that intersects the requested window
in provider order, including duplicate start stamps. Each group SHALL preserve
its end time, becoming time, change-group label and probability, plus wind,
gust, visibility, present-weather text and up to six ordered cloud layers with
existing canonical conversions. Missing values remain missing. Unsupported or
invalid rows SHALL refuse the whole report rather than disappear.

#### Scenario: Overlapping change groups keep provider order
- **WHEN** FM, TEMPO, BECMG or probability groups share a start time
- **THEN** their artifact order and native group metadata match the response

#### Scenario: Gust is absent
- **WHEN** a group carries no `wgst`
- **THEN** `wind_gust_10m` is missing for that group and is not inferred from sustained wind
