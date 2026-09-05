"""The field catalogue: the one place a field key means something.

Three adapters used to declare a manifest field named ``total_cloud`` and two of
them were not the same quantity. HRDPS cloud is opacity-weighted, so thin cirrus
reads near zero; GFS cloud is a geometric maximum-random overlap fraction; GEFS
cloud is a six-hour mean under the same word. Nothing stopped the collision,
because the names adapters declared were conventions with no registry behind
them, and a colour ramp cannot tell the difference.

This module is that registry. A **field** is one physical quantity at one level
with one unit and one declared phase. Two quantities never share a key. Related
but non-identical quantities are grouped in a **family**, which carries the
comparability note, so an activity profile has a name to ask for ("cloud cover")
without the evidence layer pretending its members are interchangeable.

The catalogue is the single source of truth for the API and the interface as
well as for ingest. Everything either of those needs is reachable through the
small query surface at the bottom of this file:

    field(key)                  -> Field
    resolve(name)               -> Resolved(field, level)
    family(name)                -> Family
    members(family_name)        -> tuple[str, ...]
    comparability(a, b, ...)    -> Comparability
    source_mapping(source_id)   -> tuple[SourceField, ...]
    storage_of(source_id, key)  -> "stored" | "available-not-stored" | "not-published"
    available_not_stored(...)   -> tuple[SourceField, ...]

Nothing here promotes a registry status: a field's ``storage`` says what this
deployment fetches, which is a scope decision, not a state a source may reach.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

CATALOGUE_VERSION = "1.0.0"
AS_OF = "2026-09-02"

#: Below this temperature relative humidity over liquid water and over a mixed
#: phase stop being the same reading; above it they agree. Measured 2026-09-01
#: against each producer's own specific humidity: at -25 degC GFS reads about
#: 24 percent higher than HRDPS for identical air.
FREEZING_K = 273.16

#: The attribute a humidity value carries its phase in, and the two phases the
#: catalogue recognises. The attribute's own values are the measured convention
#: strings ``ingest.grib.declare_rh_phase`` stamps, which name the saturation
#: function rather than the phase; ``phase_from_convention`` is the one place
#: that translation happens, so a reader never has to pattern-match a string.
PHASE_ATTRIBUTE = "rh_phase_convention"
PHASES = ("liquid", "mixed")
PHASE_BY_CONVENTION = {
    "liquid_water": "liquid",
    "mixed_linear_253K_273K": "mixed",
}


def phase_from_convention(convention: str | None) -> str | None:
    """The catalogue phase for a measured saturation convention, or None.

    None means the convention is unrecognised, which is not the same as absent:
    a value carrying a convention nobody has mapped is refused rather than
    guessed at, because the whole point of the phase is that a threshold
    calibrated on one is not transferable to the other.
    """
    if not convention:
        return None
    return PHASE_BY_CONVENTION.get(str(convention).strip())


#: What a per-source mapping may say about a field. ``available-not-stored`` is
#: the one this change adds: the producer publishes the field, this deployment
#: does not fetch it, and that is a different answer from "not retrieved" and
#: from "blocked".
STORAGE_STATES = ("stored", "available-not-stored", "not-published")

#: The six evidence classes, in the glossary's order. Repeated here rather than
#: imported so the catalogue has no dependency on ingest or on the API.
EVIDENCE_CLASSES = (
    "retrieved",
    "reprocessed",
    "derived_here",
    "intermediary_derived",
    "generated_display",
    "uncalibrated_observation",
)

_RETRIEVED = ["retrieved"]
_RETRIEVED_OR_REPROCESSED = ["retrieved", "reprocessed"]
_DERIVED = ["derived_here"]
_OBSERVED = ["retrieved", "uncalibrated_observation"]


class UnknownFieldKey(KeyError):
    """A key the catalogue does not carry. Never a warning; always a refusal."""


class UnknownFamily(KeyError):
    """A family the catalogue does not carry."""


# ---------------------------------------------------------------------------
# Families. The note is the load-bearing part: it is what a response quotes
# when it says two members are not comparable, and what the interface prints
# beside a legend it has just changed.
# ---------------------------------------------------------------------------

FAMILIES: list[dict[str, Any]] = [
    {
        "name": "cloud_cover",
        "title": "Cloud cover",
        "note": (
            "Members measure how much sky is covered, by four incompatible definitions. "
            "Opacity-weighted cover (ECCC GEM 'NT') weights each layer by how much light it "
            "actually stops, so thin cirrus reads near zero. Geometric cover (GFS, ECMWF, ICON) "
            "is a maximum-random overlap of layer fractions and counts thin cirrus in full. "
            "A six-hour mean (GEFS) is a time average and is never an instant. Observed dome "
            "cover (METAR oktas) is one observer's fraction of the celestial dome at one point. "
            "Satellite layered fraction (GOES ABI Cloud Cover Layers) is a retrieval per "
            "vertical layer. Values from different definitions must never share a colour ramp, "
            "an axis or a difference view."
        ),
        "groups": {
            "opacity_weighted_column": "Opacity-weighted whole-column cover, instantaneous.",
            "geometric_column": "Geometric maximum-random overlap whole-column fraction, instantaneous.",
            "time_mean_column": "Column cover averaged over a stated window, never an instant.",
            "observed_dome": "An observer's fraction of the celestial dome, reported in eighths.",
            "provider_stratum": "The producer's own low/middle/high layer fraction, geometric.",
            "satellite_layer": "Satellite-retrieved fraction in one vertical layer of a layered product.",
            "observed_layer": "An observer's reported cover for one reported cloud layer.",
            "derived_repair": "A derived-here repair of a producer's column cover; never the producer's value.",
            "scene_class": "A categorical clear/cloudy scene classification, not a fraction.",
        },
    },
    {
        "name": "cloud_geometry",
        "title": "Cloud geometry",
        "note": (
            "Heights and pressures of cloud boundaries. A satellite cloud-top height is a "
            "radiative retrieval of the highest opaque surface; an observer's layer base is the "
            "height a human judged a base to be at over one station. They answer different "
            "questions and are not comparable."
        ),
        "groups": {
            "satellite_top": "Radiatively retrieved cloud-top height or pressure.",
            "observed_base": "Observer-reported base of one reported layer, above ground.",
        },
    },
    {
        "name": "temperature",
        "title": "Temperature",
        "note": (
            "Air temperature at a stated level, plus surface temperatures that are not air "
            "temperature at all. A screen temperature and a skin or radiative surface "
            "temperature are different quantities and are not comparable; whether ECCC's "
            "'aggregate land surface skin temperature' and 'aggregate surface radiative "
            "temperature' are the same quantity is unverified and they are kept apart."
        ),
        "groups": {
            "air": "Air temperature at a stated height or pressure level.",
            "skin": "Aggregate land surface skin temperature.",
            "radiative": "Aggregate surface radiative temperature; not verified equal to skin.",
        },
    },
    {
        "name": "humidity",
        "title": "Humidity",
        "note": (
            "Relative humidity, specific humidity, dew point and column water vapour. Relative "
            "humidity carries a required phase attribute: HRDPS and RDPS divide by saturation "
            "over liquid water at every temperature, GFS by a mixed-phase saturation ramping "
            "from ice at 253.16 K to water at 273.16 K. The two agree above freezing and differ "
            "by up to about 24 percent below it, so a liquid-versus-mixed pair is flagged not "
            "comparable whenever either value's air temperature is below 273.16 K. Specific "
            "humidity, dew point and precipitable water carry no phase ambiguity and are "
            "separate quantities, not relative humidity in other clothes."
        ),
        "groups": {
            "relative": "Relative humidity, phase-dependent below freezing.",
            "specific": "Mass of water vapour per mass of moist air.",
            "dew_point": "Dew-point temperature.",
            "column_vapour": "Vertically integrated water vapour over the whole column.",
        },
    },
    {
        "name": "wind",
        "title": "Wind",
        "note": (
            "Wind as components and wind as speed and direction are the same vector in two "
            "encodings and are comparable within an encoding. A source stores what it publishes: "
            "GeoMet publishes speed and direction and no components anywhere, GRIB feeds publish "
            "components. Speed and direction reconstructed from components are derived-here and "
            "are served beside the raw values, never in place of them. Where a producer publishes "
            "speed only (REPS), direction stays null and nothing derives one."
        ),
        "groups": {
            "component": "Grid-relative u and v components of the horizontal wind.",
            "speed": "Scalar horizontal wind speed.",
            "direction": "Bearing the wind comes from, meteorological convention.",
            "gust": "Peak gust over the producer's own reporting interval.",
        },
    },
    {
        "name": "vertical_motion",
        "title": "Vertical motion",
        "note": "Pressure-coordinate vertical velocity. Positive omega is descent.",
        "groups": {"omega": "Vertical velocity in pressure coordinates."},
    },
    {
        "name": "pressure",
        "title": "Pressure and geopotential",
        "note": (
            "Mean sea level pressure is reduced to sea level by the producer's own reduction; "
            "surface pressure is the pressure at the model's own orography. They differ by the "
            "station's elevation and are not comparable."
        ),
        "groups": {
            "mean_sea_level": "Pressure reduced to mean sea level by the producer.",
            "surface": "Pressure at the producer's own surface height.",
            "geopotential": "Geopotential height of a pressure surface.",
        },
    },
    {
        "name": "terrain",
        "title": "Terrain",
        "note": "Static model geometry. Not a forecast and not comparable with any of it.",
        "groups": {"orography": "The model's own surface height above the geoid."},
    },
    {
        "name": "boundary_layer",
        "title": "Boundary layer",
        "note": (
            "Boundary-layer depth diagnostics. Each producer diagnoses the top by its own "
            "criterion, so values are comparable only within one producer's definition."
        ),
        "groups": {"depth": "Diagnosed planetary boundary layer height above ground."},
    },
    {
        "name": "visibility",
        "title": "Visibility and fog",
        "note": (
            "Horizontal visibility, and the fog states read from it. An observed prevailing "
            "visibility is a human or instrument reading at one station; a model visibility is a "
            "diagnosis on a grid cell. A fog state derived here from present-weather codes is a "
            "derived-here classification and is never the producer's own observation."
        ),
        "groups": {
            "horizontal": "Prevailing horizontal visibility.",
            "present_weather_flag": "A flag read out of the coded present-weather group.",
            "derived_state": "A derived-here fog classification.",
        },
    },
    {
        "name": "precipitation",
        "title": "Precipitation",
        "note": (
            "An accumulation over a stated interval, an instantaneous rate and a radar echo flag "
            "are three different quantities. An accumulation over one hour and one over three "
            "hours are not comparable without the interval, which travels with the value."
        ),
        "groups": {
            "accumulation": "Depth accumulated over the producer's own stated interval.",
            "rate": "Instantaneous precipitation rate.",
            "type": "Categorical precipitation type.",
            "echo": "Radar detection flag; its zero means 'looked and saw nothing'.",
        },
    },
    {
        "name": "lightning",
        "title": "Lightning",
        "note": (
            "A detection flag and a flash density over a stated interval. An interval with no "
            "flashes is a complete answer, not a gap."
        ),
        "groups": {
            "detection": "Whether any flash was detected in the interval.",
            "density": "Flash density over the producer's own interval.",
        },
    },
    {
        "name": "radiation",
        "title": "Surface radiation",
        "note": (
            "Every ECCC global-radiation coverage is an accumulation in J/m2 over a window the "
            "producer does not state in its title. Differencing consecutive steps for a mean flux "
            "would be derived-here, so an accumulation and a flux are separate keys and are not "
            "comparable."
        ),
        "groups": {
            "accumulated": "Accumulated radiant energy over the producer's own window.",
            "flux": "Instantaneous radiant flux density.",
        },
    },
    {
        "name": "air_quality",
        "title": "Air quality and aerosol",
        "note": (
            "Particulate mass and aerosol optical depth are not the same quantity and no "
            "conversion between them is a measurement. Mass carries no wavelength dependence and "
            "no hygroscopic growth; a mass-to-extinction conversion is a citable method and must "
            "be declared derived-here. A surface concentration and a column burden are also not "
            "comparable. The health index is a categorical scale, not a concentration."
        ),
        "groups": {
            "surface_mass": "Mass concentration at the surface.",
            "column_mass": "Mass burden integrated over the whole column.",
            "optical_depth": "Aerosol optical depth at a stated wavelength.",
            "health_index": "A categorical public-health index.",
        },
    },
    {
        "name": "hazard",
        "title": "Hazards in force",
        "note": "Counts and categories of issued warnings. Never a physical quantity.",
        "groups": {"alert_count": "Number of alerts in force over the sampled area."},
    },
    {
        "name": "transparency",
        "title": "Sky transparency",
        "note": (
            "Four incompatible encodings of 'how clear the sky is'. ECCC's RDPS sky transparency "
            "index is an unlabelled integer class 0-4 whose class definitions could not be "
            "verified from any machine-readable source, and whose 0 may be a class or a "
            "not-computed sentinel; naked-eye limiting magnitude is a magnitude; extinction is "
            "magnitudes per air mass; and Clear Sky Chart's encoding is column water vapour, "
            "which is a moisture quantity and is served under precipitable_water in the humidity "
            "family, never as a transparency. No two of these are comparable, and none is "
            "convertible into another without a declared derivation."
        ),
        "groups": {
            "class_index": "An unlabelled producer class index; the class definitions are not published.",
            "limiting_magnitude": "Faintest naked-eye stellar magnitude at the zenith.",
            "extinction": "Atmospheric extinction in magnitudes per air mass.",
        },
    },
    {
        "name": "seeing",
        "title": "Astronomical seeing",
        "note": (
            "ECCC's RDPS seeing index is an unlabelled integer class 0-5 on the same footing as "
            "its transparency index. A derived-here arcsecond estimate from a Cn2 "
            "parameterisation is a physical angle. They are not comparable, and there is no "
            "seeing monitor, DIMM or Cn2 profiler anywhere near the evidence box, so a derived "
            "seeing field can be compared with ECCC's index and never validated against a "
            "measurement."
        ),
        "groups": {
            "class_index": "An unlabelled producer class index; the class definitions are not published.",
            "angular": "Angular full width at half maximum of a stellar image.",
        },
    },
    {
        "name": "space_weather",
        "title": "Space weather",
        "note": (
            "Geomagnetic indices, solar-wind conditions at L1 and an aurora probability. The "
            "planetary indices are different instruments on different cadences: Kp is 3-hourly, "
            "Hp30 half-hourly, Hp60 hourly, Dst hourly and none is a resampling of another. "
            "Solar-wind values at L1 have not yet reached the magnetosphere; a propagated value "
            "and an L1 value are not the same instant and are not comparable. The RTSW feed "
            "interleaves three spacecraft (SOLAR-1, ACE, IMAP) with no active flag set, so a "
            "value without a spacecraft identity cannot be weighed."
        ),
        "groups": {
            "planetary_index": "A planetary geomagnetic activity index on the producer's own cadence.",
            "ring_current_index": "A ring-current index in nanotesla.",
            "imf": "Interplanetary magnetic field at the measuring spacecraft.",
            "solar_wind_plasma": "Solar-wind plasma bulk properties at the measuring spacecraft.",
            "aurora_probability": "Modelled probability of visible aurora over a grid cell.",
            "xray_flux": "Solar soft X-ray flux in a stated passband.",
        },
    },
    {
        "name": "marine",
        "title": "Marine",
        "note": (
            "Sea state, sea surface temperature, currents, ice and surge. A significant wave "
            "height that combines wind wave and swell is not comparable with either partition "
            "alone. A modelled sea surface temperature and a satellite skin SST are different "
            "measurements of a stratified surface."
        ),
        "groups": {
            "sea_surface_temperature": "Temperature of the sea surface layer.",
            "wave_height": "Height statistic of the combined sea state.",
            "wave_partition": "Height of one partition of the sea state.",
            "wave_direction": "Mean direction of the sea state.",
            "wave_period": "Mean or peak period of the sea state.",
            "current": "Horizontal sea-water velocity component.",
            "ice": "Fraction of the cell covered by sea ice.",
            "surge": "Water level departure attributable to meteorological forcing.",
            "salinity": "Sea-water salinity.",
        },
    },
    {
        "name": "astronomy_geometry",
        "title": "Sun and Moon geometry",
        "note": (
            "Positions and phases computed here from the pinned JPL DE442 ephemeris by a "
            "registered geometry method. Every member is derived-here: no producer publishes "
            "these for this site, and they are never presented as producer output. They are "
            "comparable with each other only in the trivial sense of sharing one ephemeris and "
            "one method version, which travel with every value."
        ),
        "groups": {
            "altitude": "Geometric altitude above the horizon, unrefracted unless stated.",
            "azimuth": "Bearing east of true north.",
            "phase": "Illumination geometry of the Moon.",
            "separation": "Angular separation between two bodies.",
            "twilight": "Categorical twilight state from the Sun's altitude.",
        },
    },
]


# ---------------------------------------------------------------------------
# Fields. One physical quantity per key.
#
# The level convention: height fields carry the level in the key (_2m, _10m,
# _40m, _80m, _120m). Pressure-level fields are ONE profile field with a level
# coordinate, never one key per level; ``level_suffix_pattern`` is what lets a
# level-expanded artifact variable (relative_humidity_850hPa, as the GRIB
# adapters write it today) resolve back to its one key and its level.
# ---------------------------------------------------------------------------

def _f(
    key: str,
    quantity: str,
    units: str | None,
    family: str,
    level: str,
    group: str,
    description: str,
    *,
    standard_name: str | None = None,
    evidence_classes: Sequence[str] = _RETRIEVED_OR_REPROCESSED,
    phase_attribute: bool = False,
    level_coordinate: str | None = None,
    level_suffix_pattern: str | None = None,
    value_range: tuple[float, float] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "quantity": quantity,
        "units": units,
        "family": family,
        "level": level,
        "level_coordinate": level_coordinate,
        "level_suffix_pattern": level_suffix_pattern,
        "standard_name": standard_name,
        "comparability_group": group,
        "evidence_classes": list(evidence_classes),
        "phase_attribute": phase_attribute,
        "range": list(value_range) if value_range else None,
        "description": description,
    }


_PRESSURE_SUFFIX = r"^{stem}_(?P<level>\d+)hPa$"

FIELDS: list[dict[str, Any]] = [
    # --- temperature -------------------------------------------------------
    _f("temperature_2m", "air temperature", "degC", "temperature", "2 m", "air",
       "Screen-level air temperature.", standard_name="air_temperature"),
    _f("temperature_40m", "air temperature", "degC", "temperature", "40 m", "air",
       "Air temperature at 40 m above ground. HRDPS publishes it as _TT_40m; RDPS and GDPS as "
       "AirTemp_40m.", standard_name="air_temperature"),
    _f("temperature_80m", "air temperature", "degC", "temperature", "80 m", "air",
       "Air temperature at 80 m above ground.", standard_name="air_temperature"),
    _f("temperature_120m", "air temperature", "degC", "temperature", "120 m", "air",
       "Air temperature at 120 m above ground.", standard_name="air_temperature"),
    _f("temperature_pressure", "air temperature", "degC", "temperature", "pressure levels", "air",
       "Air temperature on pressure surfaces. One field with a level coordinate; the GRIB "
       "adapters write it level-expanded as temperature_<hPa>hPa and it resolves back to here.",
       standard_name="air_temperature", level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="temperature")),
    _f("skin_temperature", "surface skin temperature", "degC", "temperature", "surface", "skin",
       "Aggregate land surface skin temperature (HRDPS _SKINT). Not air temperature and not "
       "verified equal to RDPS/GDPS aggregate surface radiative temperature.",
       standard_name="surface_temperature"),
    _f("radiative_surface_temperature", "surface radiative temperature", "degC", "temperature",
       "surface", "radiative",
       "Aggregate surface radiative temperature (RDPS/GDPS RadiativeTemp). Kept apart from "
       "skin_temperature because their equality is unverified and the air-sea difference that "
       "drives Grand Banks advection fog depends on which one is meant."),

    # --- humidity ----------------------------------------------------------
    _f("relative_humidity_2m", "relative humidity", "percent", "humidity", "2 m", "relative",
       "Screen-level relative humidity. Carries the producer's saturation phase as a required "
       "attribute; a liquid value and a mixed value are not comparable below 273.16 K.",
       standard_name="relative_humidity", phase_attribute=True, value_range=(0.0, 100.0)),
    _f("relative_humidity_40m", "relative humidity", "percent", "humidity", "40 m", "relative",
       "Relative humidity at 40 m (HRDPS _HR_40m; RDPS and GDPS publish specific humidity only "
       "at this level).", standard_name="relative_humidity", phase_attribute=True,
       value_range=(0.0, 100.0)),
    _f("relative_humidity_80m", "relative humidity", "percent", "humidity", "80 m", "relative",
       "Relative humidity at 80 m.", standard_name="relative_humidity", phase_attribute=True,
       value_range=(0.0, 100.0)),
    _f("relative_humidity_120m", "relative humidity", "percent", "humidity", "120 m", "relative",
       "Relative humidity at 120 m.", standard_name="relative_humidity", phase_attribute=True,
       value_range=(0.0, 100.0)),
    _f("relative_humidity_pressure", "relative humidity", "percent", "humidity", "pressure levels",
       "relative",
       "Relative humidity on pressure surfaces: one field with a level coordinate. GeoMet already "
       "stores it that way; the GRIB adapters write it level-expanded as "
       "relative_humidity_<hPa>hPa and it resolves back to here.",
       standard_name="relative_humidity", phase_attribute=True, value_range=(0.0, 100.0),
       level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="relative_humidity")),
    _f("specific_humidity_2m", "specific humidity", "kg kg-1", "humidity", "2 m", "specific",
       "Mass of water vapour per mass of moist air at screen level. Carries no phase ambiguity, "
       "which is why it is what the phase attribute on relative humidity is measured against.",
       standard_name="specific_humidity"),
    _f("specific_humidity_40m", "specific humidity", "kg kg-1", "humidity", "40 m", "specific",
       "Specific humidity at 40 m. The only humidity RDPS and GDPS publish at this level.",
       standard_name="specific_humidity"),
    _f("specific_humidity_80m", "specific humidity", "kg kg-1", "humidity", "80 m", "specific",
       "Specific humidity at 80 m.", standard_name="specific_humidity"),
    _f("specific_humidity_120m", "specific humidity", "kg kg-1", "humidity", "120 m", "specific",
       "Specific humidity at 120 m.", standard_name="specific_humidity"),
    _f("dew_point_2m", "dew point temperature", "degC", "humidity", "2 m", "dew_point",
       "Screen-level dew point.", standard_name="dew_point_temperature"),
    _f("dew_point_40m", "dew point temperature", "degC", "humidity", "40 m", "dew_point",
       "Dew point at 40 m (HRDPS _TD_40m; RDPS and GDPS publish DewPoint_2m only).",
       standard_name="dew_point_temperature"),
    _f("dew_point_80m", "dew point temperature", "degC", "humidity", "80 m", "dew_point",
       "Dew point at 80 m.", standard_name="dew_point_temperature"),
    _f("dew_point_120m", "dew point temperature", "degC", "humidity", "120 m", "dew_point",
       "Dew point at 120 m.", standard_name="dew_point_temperature"),
    _f("precipitable_water", "column water vapour", "kg m-2", "humidity",
       "entire atmosphere (column)", "column_vapour",
       "Vertically integrated water vapour. This is the quantity Clear Sky Chart encodes as "
       "'transparency'; it is served here as the moisture field it is and never under the "
       "transparency family. No ECCC model publishes it: GFS PWAT and GOES TPW are the only "
       "paths into the evidence box.", standard_name="atmosphere_mass_content_of_water_vapor"),

    # --- wind --------------------------------------------------------------
    _f("wind_u_10m", "eastward wind component", "m s-1", "wind", "10 m", "component",
       "Eastward component of the 10 m wind.", standard_name="eastward_wind"),
    _f("wind_v_10m", "northward wind component", "m s-1", "wind", "10 m", "component",
       "Northward component of the 10 m wind.", standard_name="northward_wind"),
    _f("wind_speed_10m", "wind speed", "m s-1", "wind", "10 m", "speed",
       "Scalar 10 m wind speed as the producer publishes it, or derived here from components; "
       "the class says which.", standard_name="wind_speed",
       evidence_classes=["retrieved", "reprocessed", "derived_here"]),
    _f("wind_direction_10m", "wind direction", "degree", "wind", "10 m", "direction",
       "Bearing the 10 m wind comes from, meteorological convention. Stays null for a "
       "speed-only product; nothing derives a direction from a speed.",
       standard_name="wind_from_direction",
       evidence_classes=["retrieved", "reprocessed", "derived_here"], value_range=(0.0, 360.0)),
    _f("wind_gust_10m", "wind gust speed", "m s-1", "wind", "10 m", "gust",
       "Peak gust over the producer's own reporting interval, which travels with the value.",
       standard_name="wind_speed_of_gust"),
    _f("wind_speed_40m", "wind speed", "m s-1", "wind", "40 m", "speed",
       "Wind speed at 40 m. GeoMet publishes speed and direction at 40/80/120 m and no "
       "components anywhere.", standard_name="wind_speed"),
    _f("wind_speed_80m", "wind speed", "m s-1", "wind", "80 m", "speed",
       "Wind speed at 80 m.", standard_name="wind_speed"),
    _f("wind_speed_120m", "wind speed", "m s-1", "wind", "120 m", "speed",
       "Wind speed at 120 m.", standard_name="wind_speed"),
    _f("wind_direction_40m", "wind direction", "degree", "wind", "40 m", "direction",
       "Wind direction at 40 m.", standard_name="wind_from_direction", value_range=(0.0, 360.0)),
    _f("wind_direction_80m", "wind direction", "degree", "wind", "80 m", "direction",
       "Wind direction at 80 m.", standard_name="wind_from_direction", value_range=(0.0, 360.0)),
    _f("wind_direction_120m", "wind direction", "degree", "wind", "120 m", "direction",
       "Wind direction at 120 m.", standard_name="wind_from_direction", value_range=(0.0, 360.0)),
    _f("wind_u_pressure", "eastward wind component", "m s-1", "wind", "pressure levels", "component",
       "Eastward wind on pressure surfaces: one field with a level coordinate. Written "
       "level-expanded as wind_u_<hPa>hPa by the GRIB adapters.", standard_name="eastward_wind",
       level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="wind_u")),
    _f("wind_v_pressure", "northward wind component", "m s-1", "wind", "pressure levels", "component",
       "Northward wind on pressure surfaces, level-expanded as wind_v_<hPa>hPa.",
       standard_name="northward_wind", level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="wind_v")),
    _f("wind_speed_pressure", "wind speed", "m s-1", "wind", "pressure levels", "speed",
       "Wind speed on pressure surfaces (GeoMet WSPD/WindSpeed), level-expanded as "
       "wind_speed_<hPa>hPa.", standard_name="wind_speed", level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="wind_speed")),
    _f("wind_direction_pressure", "wind direction", "degree", "wind", "pressure levels", "direction",
       "Wind direction on pressure surfaces, level-expanded as wind_direction_<hPa>hPa.",
       standard_name="wind_from_direction", level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="wind_direction")),

    # --- vertical motion ---------------------------------------------------
    _f("omega_pressure", "vertical velocity in pressure coordinates", "Pa s-1", "vertical_motion",
       "pressure levels", "omega",
       "Omega on pressure surfaces, level-expanded as omega_<hPa>hPa. Positive is descent.",
       standard_name="lagrangian_tendency_of_air_pressure", level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="omega")),

    # --- pressure and geopotential ----------------------------------------
    _f("mean_sea_level_pressure", "air pressure at mean sea level", "hPa", "pressure",
       "mean sea level", "mean_sea_level",
       "Pressure reduced to mean sea level by the producer's own reduction.",
       standard_name="air_pressure_at_mean_sea_level"),
    _f("surface_pressure", "surface air pressure", "Pa", "pressure", "surface", "surface",
       "Pressure at the producer's own surface height. Left in Pa: the hPa conversion in "
       "ingest.grib.normalize_units keys on the decoded variable name and this one decodes as "
       "'sp'.", standard_name="surface_air_pressure"),
    _f("geopotential_height_pressure", "geopotential height", "gpm", "pressure", "pressure levels",
       "geopotential",
       "Geopotential height of a pressure surface, level-expanded as "
       "geopotential_height_<hPa>hPa. Left in gpm: that is what the message declares and "
       "normalize_units has no rule for it.", standard_name="geopotential_height",
       level_coordinate="pressure",
       level_suffix_pattern=_PRESSURE_SUFFIX.format(stem="geopotential_height")),

    # --- terrain -----------------------------------------------------------
    _f("surface_height", "surface altitude", "m", "terrain", "surface (model orography)", "orography",
       "The model's own orography (HRDPS HGT_Sfc, paramId 228002, metres). Not a geopotential "
       "height; it is the AGL datum the WEonG low-cloud diagnosis is written against.",
       standard_name="surface_altitude"),

    # --- boundary layer ----------------------------------------------------
    _f("boundary_layer_height", "planetary boundary layer height", "m", "boundary_layer",
       "surface", "depth",
       "Diagnosed depth of the planetary boundary layer above ground (HRDPS _HPBL).",
       standard_name="atmosphere_boundary_layer_thickness"),

    # --- cloud cover -------------------------------------------------------
    _f("total_cloud_opacity", "opacity-weighted total cloud cover", "percent", "cloud_cover",
       "entire atmosphere (column)", "opacity_weighted_column",
       "Whole-column cloud cover weighted by how much light each layer stops, as ECCC GEM "
       "publishes it (HRDPS.CONTINENTAL_NT, RDPS_10km_TotalCloudCover, GDPS_15km_TotalCloudCover, "
       "REPS ETA_NT). Thin cirrus reads near zero. Not comparable with a geometric fraction.",
       standard_name="cloud_area_fraction", value_range=(0.0, 100.0)),
    _f("total_cloud_geometric", "geometric total cloud cover", "percent", "cloud_cover",
       "entire atmosphere (column)", "geometric_column",
       "Whole-column cloud fraction from a maximum-random overlap of layer fractions, as GFS "
       "(TCDC entire atmosphere), ECMWF (tcc) and ICON (clct) publish it. Thin cirrus counts in "
       "full. Not comparable with an opacity-weighted cover.",
       standard_name="cloud_area_fraction", value_range=(0.0, 100.0)),
    _f("total_cloud_mean_6h", "six-hour mean total cloud cover", "percent", "cloud_cover",
       "entire atmosphere (column)", "time_mean_column",
       "Column cloud cover averaged over the producer's forecast block, as GEFS publishes it: "
       "0-3 hour ave at f003 and 6 h thereafter. GEFS publishes no instantaneous column cloud at "
       "all, so this key never stands in for one and is never served under an instantaneous key.",
       standard_name="cloud_area_fraction", value_range=(0.0, 100.0)),
    _f("total_cloud_okta", "observed sky cover", "percent", "cloud_cover",
       "entire atmosphere (column)", "observed_dome",
       "One observer's fraction of the celestial dome covered, reported in eighths and converted "
       "to percent. A point observation over one station, not a grid cell, and not comparable "
       "with any modelled column cover.", standard_name="cloud_area_fraction",
       evidence_classes=_OBSERVED, value_range=(0.0, 100.0)),
    _f("total_cloud_weong", "opacity-weighted total cloud cover, WEonG low-cloud repair", "percent",
       "cloud_cover", "entire atmosphere (column)", "derived_repair",
       "ECCC's own WEonG technical note states HRDPS published NT under-reports low cloud and "
       "repairs it from the RH profile. This key carries that repair, computed here, and is "
       "always served beside total_cloud_opacity rather than replacing it.",
       standard_name="cloud_area_fraction", evidence_classes=_DERIVED, value_range=(0.0, 100.0)),
    _f("cloud_low", "low cloud cover", "percent", "cloud_cover", "low cloud layer",
       "provider_stratum",
       "The producer's own low-cloud layer fraction (GFS LCDC). A provider-declared stratum, "
       "never a classification made here. No ECCC model publishes cloud by layer on GeoMet at "
       "all.", standard_name="low_type_cloud_area_fraction", value_range=(0.0, 100.0)),
    _f("cloud_middle", "middle cloud cover", "percent", "cloud_cover", "middle cloud layer",
       "provider_stratum", "The producer's own middle-cloud layer fraction (GFS MCDC).",
       standard_name="medium_type_cloud_area_fraction", value_range=(0.0, 100.0)),
    _f("cloud_high", "high cloud cover", "percent", "cloud_cover", "high cloud layer",
       "provider_stratum", "The producer's own high-cloud layer fraction (GFS HCDC).",
       standard_name="high_type_cloud_area_fraction", value_range=(0.0, 100.0)),
    _f("cloud_fraction_layer_1", "layered cloud fraction", "percent", "cloud_cover",
       "product layer 1 (lowest)", "satellite_layer",
       "Cloud fraction in the lowest of the five vertical layers of the GOES ABI Cloud Cover "
       "Layers product. The layer boundaries are the product's own and were not verified in this "
       "deployment's research, so they travel with the value rather than being restated here.",
       value_range=(0.0, 100.0)),
    _f("cloud_fraction_layer_2", "layered cloud fraction", "percent", "cloud_cover",
       "product layer 2", "satellite_layer",
       "Cloud fraction in the second of the five GOES ABI Cloud Cover Layers layers.",
       value_range=(0.0, 100.0)),
    _f("cloud_fraction_layer_3", "layered cloud fraction", "percent", "cloud_cover",
       "product layer 3", "satellite_layer",
       "Cloud fraction in the third of the five GOES ABI Cloud Cover Layers layers.",
       value_range=(0.0, 100.0)),
    _f("cloud_fraction_layer_4", "layered cloud fraction", "percent", "cloud_cover",
       "product layer 4", "satellite_layer",
       "Cloud fraction in the fourth of the five GOES ABI Cloud Cover Layers layers.",
       value_range=(0.0, 100.0)),
    _f("cloud_fraction_layer_5", "layered cloud fraction", "percent", "cloud_cover",
       "product layer 5 (highest)", "satellite_layer",
       "Cloud fraction in the highest of the five GOES ABI Cloud Cover Layers layers.",
       value_range=(0.0, 100.0)),
    _f("cloud_mask_class", "clear-sky mask class", "code", "cloud_cover", "column", "scene_class",
       "The GOES ABI clear-sky mask's own four-value scene class. A categorical answer, not a "
       "fraction, and never averaged into one."),
    _f("cloud_probability", "cloud probability", "percent", "cloud_cover", "column", "scene_class",
       "The satellite retrieval's own confidence that the scene is cloudy. Not a cover fraction: "
       "a certainly-cloudy thin cirrus scene reads 100 here and near zero in opacity-weighted "
       "cover.", value_range=(0.0, 100.0)),

    # --- cloud geometry ----------------------------------------------------
    _f("cloud_top_height", "cloud top height", "m", "cloud_geometry", "cloud top", "satellite_top",
       "Radiatively retrieved height of the highest opaque cloud surface (GOES ABI ACHA). NOAA "
       "Provisional maturity.", standard_name="cloud_top_altitude"),
    _f("cloud_top_pressure", "cloud top pressure", "hPa", "cloud_geometry", "cloud top",
       "satellite_top", "Retrieved pressure of the cloud top (GOES ABI CTP).",
       standard_name="air_pressure_at_cloud_top"),
    _f("cloud_ceiling", "cloud ceiling height", "m", "cloud_geometry", "ceiling", "observed_base",
       "Height above ground of the lowest broken or overcast layer.",
       standard_name="cloud_base_altitude"),

    # --- visibility and fog ------------------------------------------------
    _f("visibility", "horizontal visibility", "m", "visibility", "surface", "horizontal",
       "Prevailing horizontal visibility.", standard_name="visibility_in_air",
       evidence_classes=["retrieved", "reprocessed", "uncalibrated_observation"]),
    _f("weather_fog_code", "present-weather fog flag", "flag", "visibility", "surface",
       "present_weather_flag",
       "Fog read out of the METAR/TAF present-weather group (WMO No. 306 FM 15 table 4678). "
       "Retrieved: it is what the report said, not a judgement made here. Mist (BR) is a "
       "different phenomenon and is not this flag."),
    _f("fog_state", "fog state", "code", "visibility", "surface", "derived_state",
       "A fog classification computed here from present-weather codes and visibility by a "
       "registered derivation method. Never the producer's own observation.",
       evidence_classes=_DERIVED),
    _f("fog_closure", "fog closure fraction", "1", "visibility", "surface", "derived_state",
       "The derived-here fog closure the cloud-and-fog derivation emits, on 0 to 1.",
       evidence_classes=_DERIVED, value_range=(0.0, 1.0)),

    # --- observed cloud layers (METAR/TAF) ---------------------------------
    *[
        item
        for slot in range(1, 7)
        for item in (
            _f(f"cloud_layer_{slot}_cover_code", "reported layer cover code", "code", "cloud_cover",
               f"reported cloud layer {slot}", "observed_layer",
               f"The coded sky cover (SKC/FEW/SCT/BKN/OVC/VV) of the {slot}th layer the report "
               "lists, in the producer's own order. Never folded into low/middle/high strata: "
               "that would be a classification the owner has not approved.",
               evidence_classes=_OBSERVED),
            _f(f"cloud_layer_{slot}_cover", "reported layer cover", "percent", "cloud_cover",
               f"reported cloud layer {slot}", "observed_layer",
               f"The {slot}th reported layer's cover as a percentage of the dome.",
               evidence_classes=_OBSERVED, value_range=(0.0, 100.0)),
            _f(f"cloud_layer_{slot}_base", "reported layer base height", "m", "cloud_geometry",
               f"reported cloud layer {slot}", "observed_base",
               f"Height above ground of the {slot}th reported layer's base.",
               standard_name="cloud_base_altitude", evidence_classes=_OBSERVED),
        )
    ],

    # --- precipitation -----------------------------------------------------
    _f("precipitation_accumulation", "precipitation amount", "mm", "precipitation", "surface",
       "accumulation",
       "Depth accumulated over the producer's own stated interval, which travels with the value. "
       "A one-hour and a three-hour accumulation are not comparable without it.",
       standard_name="precipitation_amount"),
    _f("precipitation_rate", "precipitation rate", "mm h-1", "precipitation", "surface", "rate",
       "Instantaneous precipitation rate.", standard_name="rainfall_rate"),
    _f("snow_rate", "snowfall rate", "cm h-1", "precipitation", "surface", "rate",
       "Instantaneous snowfall rate as depth of snow, not water equivalent.",
       standard_name="lwe_snowfall_rate"),
    _f("precipitation_type", "precipitation type", "code", "precipitation", "surface", "type",
       "Categorical precipitation type as the producer codes it."),
    _f("radar_echo", "radar echo detection flag", "flag", "precipitation",
       "radar mosaic surface projection", "echo",
       "Whether the radar mosaic detected an echo. Its zero means the mosaic looked and saw "
       "nothing, which is why it is a flag and not a rate: publishing that zero as '0 mm/h' "
       "would be a measurement nobody made."),

    # --- lightning ---------------------------------------------------------
    _f("lightning_observed", "lightning detection flag", "flag", "lightning",
       "10-minute gridded interval", "detection",
       "Whether any flash was detected in the interval. An interval with no flashes is a "
       "complete answer."),
    _f("lightning_strike", "lightning flash density", "flash km-2 min-1", "lightning",
       "10-minute gridded interval", "density",
       "Flash density over the gridded interval. Declared to the manifest only when the interval "
       "carried a value, because an all-missing declared field is refused."),

    # --- radiation ---------------------------------------------------------
    _f("downward_shortwave_accumulated", "accumulated downward shortwave radiation", "J m-2",
       "radiation", "surface", "accumulated",
       "Accumulated downward shortwave radiant energy at the surface (HRDPS _N4). Every ECCC "
       "global-radiation coverage is an accumulation; no instantaneous W/m2 coverage exists, and "
       "the accumulation window is not stated in the WMS title. Differencing steps for a flux "
       "would be derived-here.",
       standard_name="surface_downwelling_shortwave_flux_in_air_integral_wrt_time"),
    _f("downward_shortwave_flux", "downward shortwave radiation flux", "W m-2", "radiation",
       "surface", "flux",
       "Instantaneous downward shortwave flux density. A separate key from the accumulation "
       "because converting one to the other is a derivation, not a unit change.",
       standard_name="surface_downwelling_shortwave_flux_in_air"),

    # --- air quality -------------------------------------------------------
    _f("air_quality_health_index", "air quality health index", "index", "air_quality", "station",
       "health_index", "ECCC's categorical Air Quality Health Index. A scale, not a "
       "concentration."),
    _f("pm2_5_surface", "surface PM2.5 mass concentration", "kg m-3", "air_quality", "surface",
       "surface_mass", "Surface fine particulate mass concentration (RAQDPS SFC_PM2.5).",
       standard_name="mass_concentration_of_pm2p5_ambient_aerosol_particles_in_air"),
    _f("pm2_5_column", "column PM2.5 mass burden", "kg m-2", "air_quality",
       "entire atmosphere (column)", "column_mass",
       "Entire-column fine particulate mass burden (RAQDPS EATM_PM2.5). Not comparable with a "
       "surface concentration."),
    _f("pm10_surface", "surface PM10 mass concentration", "kg m-3", "air_quality", "surface",
       "surface_mass", "Surface coarse particulate mass concentration."),
    _f("aerosol_optical_depth_550nm", "aerosol optical depth at 550 nm", "1", "air_quality",
       "entire atmosphere (column)", "optical_depth",
       "Column aerosol optical depth at 550 nm. Not particulate mass: it carries wavelength "
       "dependence and hygroscopic growth that mass does not, so no conversion between them is a "
       "measurement. Every AOD path into the evidence box is credential-blocked today.",
       standard_name="atmosphere_optical_thickness_due_to_ambient_aerosol_particles"),

    # --- hazard ------------------------------------------------------------
    _f("alerts_in_force", "alerts in force", "count", "hazard", "surface", "alert_count",
       "How many ECCC public alerts cover the sampled point at the sampled instant."),

    # --- transparency ------------------------------------------------------
    _f("transparency_class_eccc", "sky transparency class index", "1", "transparency",
       "entire atmosphere (column)", "class_index",
       "ECCC RDPS sky transparency index (RDPS_10km_SkyTransparencyIndex). An unlabelled integer "
       "class; a live subset decoded to exactly {0, 2, 3, 4} across all 8113 cells and the WMS "
       "leaf title carries no unit bracket. Whether 0 is a class or a not-computed sentinel is "
       "unresolved, and CMC is documented as refusing to compute transparency above 30 percent "
       "cloud, so 0 may be a masked cell rather than 'worst'.", value_range=(0.0, 4.0)),
    _f("transparency_limiting_magnitude", "naked-eye limiting magnitude", "mag", "transparency",
       "zenith", "limiting_magnitude",
       "Faintest stellar magnitude visible to the unaided eye at the zenith. A different "
       "encoding of transparency from the class index and not convertible into it."),
    _f("transparency_extinction", "atmospheric extinction", "mag airmass-1", "transparency",
       "zenith", "extinction",
       "Atmospheric extinction in magnitudes per air mass. A third encoding, comparable with "
       "neither of the others."),

    # --- seeing ------------------------------------------------------------
    _f("seeing_class_eccc", "seeing class index", "1", "seeing", "entire atmosphere (column)",
       "class_index",
       "ECCC RDPS seeing index (RDPS_10km_SeeingIndex). An unlabelled integer class; a live "
       "subset decoded to exactly {0, 3, 4, 5}. The class definitions could not be verified from "
       "any machine-readable source and CMC is documented as refusing to compute seeing above "
       "80 percent cloud, so 0 may be a masked cell.", value_range=(0.0, 5.0)),
    _f("seeing_arcsec", "astronomical seeing", "arcsec", "seeing", "entire atmosphere (column)",
       "angular",
       "Angular full width at half maximum of a stellar image, computed here by a registered Cn2 "
       "parameterisation over the column. There is no seeing monitor, DIMM or Cn2 profiler "
       "anywhere near the evidence box, so this can be compared with the ECCC class index and "
       "never validated against a measurement.", evidence_classes=_DERIVED),

    # --- space weather -----------------------------------------------------
    _f("kp_index", "planetary K index", "1", "space_weather", "planetary", "planetary_index",
       "The 3-hourly planetary K index as retrieved.", value_range=(0.0, 9.0)),
    _f("a_running", "running a index", "1", "space_weather", "planetary", "planetary_index",
       "The running a index as retrieved beside Kp."),
    _f("kp_status", "planetary K index status", "flag", "space_weather", "planetary",
       "planetary_index",
       "The producer's own status string for a Kp value (observed, estimated, predicted), "
       "carried per value so an outlook is never read as an observation."),
    _f("hp30_index", "Hp30 geomagnetic index", "1", "space_weather", "planetary", "planetary_index",
       "GFZ's half-hourly Hp30 index. Not a resampling of Kp; a separate instrument on a "
       "separate cadence."),
    _f("hp60_index", "Hp60 geomagnetic index", "1", "space_weather", "planetary", "planetary_index",
       "GFZ's hourly Hp60 index."),
    _f("dst_index", "disturbance storm time index", "nT", "space_weather", "planetary",
       "ring_current_index",
       "The Kyoto WDC quicklook Dst. Reprocessed where it arrives through NOAA SWPC's "
       "redistribution rather than from Kyoto directly.",
       evidence_classes=_RETRIEVED_OR_REPROCESSED),
    _f("bz_gsm", "interplanetary magnetic field Bz, GSM", "nT", "space_weather",
       "measuring spacecraft at L1", "imf",
       "Southward IMF component in GSM coordinates. The RTSW feed interleaves SOLAR-1, ACE and "
       "IMAP with no active flag set, so the measuring spacecraft's identity has to travel with "
       "the value."),
    _f("bt", "interplanetary magnetic field magnitude", "nT", "space_weather",
       "measuring spacecraft at L1", "imf", "Total IMF magnitude at the measuring spacecraft."),
    _f("solar_wind_speed", "solar wind bulk speed", "km s-1", "space_weather",
       "measuring spacecraft at L1", "solar_wind_plasma",
       "Proton bulk speed at L1. An L1 value has not yet reached the magnetosphere; a propagated "
       "value is a different instant and is not comparable with it."),
    _f("solar_wind_density", "solar wind proton density", "cm-3", "space_weather",
       "measuring spacecraft at L1", "solar_wind_plasma", "Proton number density at L1."),
    _f("solar_wind_temperature", "solar wind proton temperature", "K", "space_weather",
       "measuring spacecraft at L1", "solar_wind_plasma", "Proton temperature at L1."),
    _f("aurora_probability", "aurora visibility probability", "percent", "space_weather",
       "surface", "aurora_probability",
       "SWPC OVATION modelled probability of visible aurora over a grid cell, sampled as stored. "
       "The one genuinely gridded space-weather product.",
       evidence_classes=_RETRIEVED_OR_REPROCESSED, value_range=(0.0, 100.0)),
    _f("xray_flux_long", "solar X-ray flux, 0.1-0.8 nm", "W m-2", "space_weather",
       "geosynchronous orbit", "xray_flux",
       "GOES XRS long-channel flux. Flare context, typically two to three days upstream of any "
       "aurora."),
    _f("xray_flux_short", "solar X-ray flux, 0.05-0.4 nm", "W m-2", "space_weather",
       "geosynchronous orbit", "xray_flux", "GOES XRS short-channel flux."),

    # --- marine ------------------------------------------------------------
    _f("sea_surface_temperature", "sea surface temperature", "degC", "marine", "sea surface",
       "sea_surface_temperature",
       "Temperature of the sea surface layer. A modelled bulk SST and a satellite skin SST are "
       "different measurements of a stratified surface.",
       standard_name="sea_surface_temperature"),
    _f("significant_wave_height", "significant wave height", "m", "marine", "sea surface",
       "wave_height",
       "Significant height of the combined wind wave and swell. Not comparable with either "
       "partition on its own.", standard_name="sea_surface_wave_significant_height"),
    _f("wind_wave_height", "wind wave height", "m", "marine", "sea surface", "wave_partition",
       "Significant height of the wind-sea partition."),
    _f("swell_height", "swell height", "m", "marine", "sea surface", "wave_partition",
       "Significant height of the swell partition."),
    _f("wave_direction", "wave direction", "degree", "marine", "sea surface", "wave_direction",
       "Mean direction of the sea state.", standard_name="sea_surface_wave_from_direction",
       value_range=(0.0, 360.0)),
    _f("wave_period", "wave period", "s", "marine", "sea surface", "wave_period",
       "Mean or peak period of the sea state, as the producer defines it."),
    _f("current_u", "eastward sea water velocity", "m s-1", "marine", "sea surface", "current",
       "Eastward component of the surface current.", standard_name="eastward_sea_water_velocity"),
    _f("current_v", "northward sea water velocity", "m s-1", "marine", "sea surface", "current",
       "Northward component of the surface current.",
       standard_name="northward_sea_water_velocity"),
    _f("sea_ice_fraction", "sea ice area fraction", "1", "marine", "sea surface", "ice",
       "Fraction of the cell covered by sea ice. HRDPS publishes it analysis-only: its WMS time "
       "extent advertised a single instant with PT0H, not a forecast series.",
       standard_name="sea_ice_area_fraction", value_range=(0.0, 1.0)),
    _f("storm_surge", "storm surge water level", "m", "marine", "sea surface", "surge",
       "Water level departure attributable to meteorological forcing."),
    _f("salinity", "sea water salinity", "g kg-1", "marine", "sea surface", "salinity",
       "Sea-water salinity.", standard_name="sea_water_salinity"),

    # --- astronomy geometry (all derived here from DE442) -------------------
    _f("sun_altitude", "Sun altitude", "degree", "astronomy_geometry", "topocentric", "altitude",
       "Geometric altitude of the Sun's centre above the true horizon, computed here from the "
       "pinned JPL DE442 ephemeris by the registered geometry method.",
       evidence_classes=_DERIVED, value_range=(-90.0, 90.0)),
    _f("sun_azimuth", "Sun azimuth", "degree", "astronomy_geometry", "topocentric", "azimuth",
       "Bearing of the Sun east of true north, from DE442.", evidence_classes=_DERIVED,
       value_range=(0.0, 360.0)),
    _f("moon_altitude", "Moon altitude", "degree", "astronomy_geometry", "topocentric", "altitude",
       "Geometric altitude of the Moon's centre above the true horizon, from DE442.",
       evidence_classes=_DERIVED, value_range=(-90.0, 90.0)),
    _f("moon_azimuth", "Moon azimuth", "degree", "astronomy_geometry", "topocentric", "azimuth",
       "Bearing of the Moon east of true north, from DE442.", evidence_classes=_DERIVED,
       value_range=(0.0, 360.0)),
    _f("moon_phase_angle", "Moon phase angle", "degree", "astronomy_geometry", "topocentric",
       "phase", "Sun-Moon-observer angle, from DE442.", evidence_classes=_DERIVED,
       value_range=(0.0, 180.0)),
    _f("moon_illuminated_fraction", "Moon illuminated fraction", "1", "astronomy_geometry",
       "topocentric", "phase", "Fraction of the Moon's disc illuminated, from DE442.",
       evidence_classes=_DERIVED, value_range=(0.0, 1.0)),
    _f("moon_separation", "Moon angular separation", "degree", "astronomy_geometry", "topocentric",
       "separation",
       "Angular separation between the Moon and a named target, from DE442. The target travels "
       "with the value.", evidence_classes=_DERIVED, value_range=(0.0, 180.0)),
    _f("twilight_state", "twilight state", "code", "astronomy_geometry", "topocentric", "twilight",
       "Day, civil, nautical, astronomical or night, from the Sun's DE442 altitude at the "
       "standard boundaries.", evidence_classes=_DERIVED),
]


# ---------------------------------------------------------------------------
# Per-source scope. Two shapes, and the difference is the whole storage story:
# a source that subsets server side is stored in full; a feed that cannot
# subset costs its whole file per record, so only the catalogue's family fields
# are fetched and everything else is catalogued available-not-stored.
# ---------------------------------------------------------------------------

_PROBE = "docs/research/wayfinder/size-probe-full-fields.md"

SOURCE_SCOPE: list[dict[str, Any]] = [
    {
        "source_id": "eccc-hrdps", "subsetting": "server_side", "policy": "family_fields_only",
        "published_field_count": 377, "counted_from": _PROBE,
        "note": ("GeoMet WCS subsets to the evidence box before the bytes leave the producer, so "
                 "wire and stored are the same number. The current production owner is the "
                 "Datamart GRIB adapter and stores only its declared family fields; WCS-only "
                 "fields remain available-not-stored pending source-contract acceptance. At "
                 "377 coverages HRDPS is about 5.5 GB resident and 74 percent of the core "
                 "window; its 206 pressure-level coverages are 3.02 GB of that. A coverage the "
                 "catalogue does not know blocks publication as uncatalogued_upstream_field "
                 "rather than being skipped."),
    },
    {
        "source_id": "eccc-rdps", "subsetting": "server_side", "policy": "family_fields_only",
        "published_field_count": 438, "counted_from": _PROBE,
        "note": "As HRDPS, with WCS-only fields available-not-stored, at 10 km.",
    },
    {
        "source_id": "eccc-gdps", "subsetting": "server_side", "policy": "family_fields_only",
        "published_field_count": 474, "counted_from": _PROBE,
        "note": "As HRDPS, at 15 km, including the separately inventoried 25 km GEML grid.",
    },
    {
        "source_id": "eccc-reps", "subsetting": "server_side", "policy": "every_published_field",
        "published_field_count": 1773, "counted_from": _PROBE,
        "note": ("21 members at 59 fields each plus 534 provider reductions. Members publish "
                 "wind speed and no components anywhere, so member wind direction is not "
                 "retrievable and stays null."),
    },
    {
        "source_id": "eccc-geps", "subsetting": "server_side", "policy": "every_published_field",
        "published_field_count": 532, "counted_from": _PROBE,
        "note": ("Reductions only: zero GEPS.MEM.* coverages exist. Every published field is a "
                 "provider statistic, stored as issued and never recombined."),
    },
    {
        "source_id": "noaa-gfs", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 1092, "counted_from": _PROBE,
        "note": ("743 pgrb2 plus 349 pgrb2b records per lead, with no server-side subsetting: "
                 "766 MB on the wire per lead for about 4.9 MB of box. Byte-range selection over "
                 "the .idx stops helping once every record is wanted, because the ranges become "
                 "the whole file. The catalogue's family fields are fetched by byte range and "
                 "every other record is catalogued available-not-stored."),
    },
    {
        "source_id": "noaa-gefs", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 628, "counted_from": _PROBE,
        "note": ("628 records per member across pgrb2a, pgrb2b and pgrb2s, times 31 members. "
                 "4.22 GB on the wire per lead for about 27 MB of box."),
    },
    {
        "source_id": "ecmwf-ifs", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 184, "counted_from": _PROBE,
        "note": "48 distinct parameters over sfc, pl and sol; 143 MB per lead on the wire.",
    },
    {
        "source_id": "ecmwf-ens", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 8500, "counted_from": _PROBE,
        "note": "47 distinct parameters across 51 members; 6.65 GB per lead on the wire.",
    },
    {
        "source_id": "ecmwf-aifs-single", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 122, "counted_from": _PROBE,
        "note": "30 distinct parameters; 85 MB per lead on the wire.",
    },
    {
        "source_id": "ecmwf-aifs-ens", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 5508, "counted_from": _PROBE,
        "note": "29 distinct parameters across 51 members; 4.53 GB per lead on the wire.",
    },
    {
        "source_id": "dwd-icon-global", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 1288, "counted_from": _PROBE,
        "note": ("1288 files per lead over 84 time-varying variables, the bulk of them "
                 "multi-level expansions: t, u, v at 138 levels, qc/qi/qv/p at 120, clc at 82, "
                 "tke at 61, relhum at 18. 3.109 GB per lead on the wire for about 22 MB of box, "
                 "a ratio of 138 to 1."),
    },
    {
        "source_id": "dwd-icon-eps", "subsetting": "none", "policy": "family_fields_only",
        "published_field_count": 0, "counted_from": "none",
        "note": ("ICON-EPS is sixth in the owner's admission order natively, because nothing "
                 "about it was measured on wayfinder ticket #22: no field list, no member count, "
                 "no access path and no size figure. published_field_count is 0 and counted_from "
                 "is 'none' because no probe was ever run against it, not because it publishes "
                 "nothing. No field is mapped for it below; every field it would store is left "
                 "for the measurement task design.md's owner gate 6.3 calls for, rather than "
                 "guessed at here."),
    },
]


def _sf(source_id: str, key: str, upstream: str | None, storage: str, note: str,
        phase: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source_id": source_id, "key": key, "upstream": upstream, "storage": storage, "note": note,
    }
    if phase is not None:
        entry["phase"] = phase
    return entry


_ECCC_LIQUID = ("Measured 2026-09-01 against the model's own specific humidity: divides by "
                "saturation over liquid water at every temperature.")
_GFS_MIXED = ("Measured 2026-09-01 against the model's own specific humidity: divides by a "
              "mixed-phase saturation ramping linearly from ice at 253.16 K to water at "
              "273.16 K, so it reads about 24 percent higher than a liquid-basis value at "
              "-25 degC.")

SOURCE_FIELDS: list[dict[str, Any]] = [
    # --- ECCC GEM, opacity-weighted cloud, liquid-basis humidity -----------
    _sf("eccc-hrdps", "total_cloud_opacity", "HRDPS.CONTINENTAL_NT", "stored",
        "Title verified 'Total cloud cover [%]'. The opacity-weighted quantity."),
    _sf("eccc-hrdps", "relative_humidity_2m", "HRDPS.CONTINENTAL_HR", "stored",
        _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-hrdps", "temperature_2m", "HRDPS.CONTINENTAL_TT", "stored", "Verified live."),
    _sf("eccc-hrdps", "dew_point_2m", "HRDPS.CONTINENTAL_TD", "stored", "Title verified."),
    _sf("eccc-hrdps", "mean_sea_level_pressure", "HRDPS.CONTINENTAL_PN-SLP", "stored",
        "Published in Pa and normalized to hPa on ingest."),
    _sf("eccc-hrdps", "wind_speed_10m", "HRDPS.CONTINENTAL_WSPD", "stored",
        "GeoMet publishes speed and direction and no u/v components anywhere, for any ECCC "
        "model, at any level."),
    _sf("eccc-hrdps", "wind_direction_10m", "HRDPS.CONTINENTAL_WD", "stored", "As the speed."),
    _sf("eccc-hrdps", "wind_u_10m", None, "not-published",
        "No u/v anywhere on GeoMet WCS or WMS. The components this deployment serves from the "
        "GeoMet path are reconstructed here from speed and direction and carry that class."),
    _sf("eccc-hrdps", "wind_v_10m", None, "not-published", "As wind_u_10m."),
    _sf("eccc-hrdps", "precipitation_accumulation", "HRDPS.CONTINENTAL.DIAG_PR_PT1H", "stored",
        "One-hour accumulation; the interval travels with the value."),
    _sf("eccc-hrdps", "relative_humidity_pressure", "HRDPS.CONTINENTAL.PRES_HR.<hPa>", "stored",
        "GeoMet advertises 28 levels from 50 to 1015 hPa. The production Datamart adapter stores "
        "its declared nine-level low-cloud profile; the other WCS levels remain capability-only. "
        + _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-hrdps", "relative_humidity_40m", "HRDPS.CONTINENTAL_HR_40m", "available-not-stored",
        "Title verified, [%]. " + _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-hrdps", "relative_humidity_80m", "HRDPS.CONTINENTAL_HR_80m", "available-not-stored",
        _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-hrdps", "relative_humidity_120m", "HRDPS.CONTINENTAL_HR_120m", "available-not-stored",
        _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-hrdps", "temperature_40m", "HRDPS.CONTINENTAL_TT_40m", "available-not-stored", "Verified live WCS capability; production storage pending."),
    _sf("eccc-hrdps", "temperature_80m", "HRDPS.CONTINENTAL_TT_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-hrdps", "temperature_120m", "HRDPS.CONTINENTAL_TT_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-hrdps", "specific_humidity_40m", "HRDPS.CONTINENTAL_HU_40m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-hrdps", "specific_humidity_80m", "HRDPS.CONTINENTAL_HU_80m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-hrdps", "specific_humidity_120m", "HRDPS.CONTINENTAL_HU_120m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-hrdps", "dew_point_40m", "HRDPS.CONTINENTAL_TD_40m", "available-not-stored",
        "Title verified 'Dew point temperature at 40m above ground'. RDPS and GDPS publish "
        "DewPoint_2m only."),
    _sf("eccc-hrdps", "dew_point_80m", "HRDPS.CONTINENTAL_TD_80m", "available-not-stored", "Title verified."),
    _sf("eccc-hrdps", "dew_point_120m", "HRDPS.CONTINENTAL_TD_120m", "available-not-stored", "Verified live WCS capability."),
    _sf("eccc-hrdps", "wind_speed_40m", "HRDPS.CONTINENTAL_WSPD_40m", "available-not-stored",
        "GeoMet publishes speed and direction at height, never components."),
    _sf("eccc-hrdps", "wind_speed_80m", "HRDPS.CONTINENTAL_WSPD_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-hrdps", "wind_speed_120m", "HRDPS.CONTINENTAL_WSPD_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-hrdps", "wind_direction_40m", "HRDPS.CONTINENTAL_WD_40m", "available-not-stored", "As 40 m."),
    _sf("eccc-hrdps", "wind_direction_80m", "HRDPS.CONTINENTAL_WD_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-hrdps", "wind_direction_120m", "HRDPS.CONTINENTAL_WD_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-hrdps", "boundary_layer_height", "HRDPS.CONTINENTAL_HPBL", "available-not-stored",
        "Title verified 'Planetary boundary layer height [m]'."),
    _sf("eccc-hrdps", "skin_temperature", "HRDPS.CONTINENTAL_SKINT", "available-not-stored",
        "Title verified 'Aggregate land surface skin temperature [degC]'."),
    _sf("eccc-hrdps", "sea_ice_fraction", "HRDPS.CONTINENTAL_ICEC", "available-not-stored",
        "Analysis-only: the WMS time extent advertised one instant with PT0H, not a forecast "
        "series. Whether that is permanent is unverified."),
    _sf("eccc-hrdps", "downward_shortwave_accumulated", "HRDPS.CONTINENTAL_N4", "available-not-stored",
        "Title verified 'Downward shortwave accumulated radiation flux at the surface [J/m2]'. "
        "The WCS range type calls it W.m-2.Sr-1 and is not trustworthy."),
    _sf("eccc-hrdps", "surface_height", "HGT_Sfc", "stored",
        "Decodes as orography, paramId 228002, metres. The AGL datum WEonG needs."),
    _sf("eccc-hrdps", "cloud_low", None, "not-published",
        "Cloud by layer does not exist on GeoMet WCS for any ECCC model: a grep of all 6123 "
        "coverage ids returns only TotalCloudCover, CloudWater_EAtm and the two HRDPS codes."),
    _sf("eccc-hrdps", "cloud_middle", None, "not-published", "As cloud_low."),
    _sf("eccc-hrdps", "cloud_high", None, "not-published", "As cloud_low."),
    _sf("eccc-hrdps", "cloud_ceiling", None, "not-published",
        "Cloud base and ceiling are not on GeoMet WCS for any ECCC model."),
    _sf("eccc-hrdps", "precipitable_water", None, "not-published",
        "Nothing in the 6123 advertised coverages matches precipitable water, integrated water "
        "vapour or total column water vapour for HRDPS, RDPS or GDPS. The only PW* ids are GDWPS "
        "wave-period layers, and CloudWater_EAtm is condensate, not vapour."),
    _sf("eccc-hrdps", "total_cloud_weong", "HRDPS-WEonG_2.5km_SkyState", "available-not-stored",
        "GeoMet advertises this categorical proxy and the isolated WCS experiment retrieved it; "
        "the production adapter is still the Datamart GRIB path and does not store this coverage."),

    _sf("eccc-rdps", "total_cloud_opacity", "RDPS_10km_TotalCloudCover", "stored",
        "The same opacity-weighted quantity as HRDPS NT; comparable with it."),
    _sf("eccc-rdps", "relative_humidity_2m", "RDPS_10km_RelativeHumidity_2m", "stored",
        _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-rdps", "temperature_2m", "RDPS_10km_AirTemp_2m", "stored", "Verified live."),
    _sf("eccc-rdps", "dew_point_2m", "RDPS_10km_DewPoint_2m", "stored", "Verified live."),
    _sf("eccc-rdps", "mean_sea_level_pressure", "RDPS_10km_Pressure_MSL", "stored",
        "Published in Pa and normalized to hPa on ingest."),
    _sf("eccc-rdps", "wind_speed_10m", "RDPS_10km_WindSpeed_10m", "stored", "Speed and direction."),
    _sf("eccc-rdps", "wind_direction_10m", "RDPS_10km_WindDir_10m", "stored", "As the speed."),
    _sf("eccc-rdps", "wind_u_10m", None, "not-published", "No u/v anywhere on GeoMet."),
    _sf("eccc-rdps", "wind_v_10m", None, "not-published", "As wind_u_10m."),
    _sf("eccc-rdps", "precipitation_accumulation", "RDPS_10km_Precip-Accum1h", "stored",
        "One-hour accumulation."),
    _sf("eccc-rdps", "temperature_40m", "RDPS_10km_AirTemp_40m", "available-not-stored", "Verified live WCS capability; production storage pending."),
    _sf("eccc-rdps", "temperature_80m", "RDPS_10km_AirTemp_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "temperature_120m", "RDPS_10km_AirTemp_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "relative_humidity_pressure", "RDPS_10km_RelativeHumidity_<n>mb", "stored",
        "GeoMet advertises 31 levels plus 2 m, adding 10, 20 and 30 mb to the HRDPS set. The "
        "production Datamart adapter stores its declared subset; the other WCS levels remain "
        "capability-only. " + _ECCC_LIQUID,
        phase="liquid"),
    _sf("eccc-rdps", "specific_humidity_40m", "RDPS_10km_SpecificHumidity_40m", "available-not-stored",
        "RDPS publishes no relative humidity at 40/80/120 m, only specific humidity."),
    _sf("eccc-rdps", "specific_humidity_80m", "RDPS_10km_SpecificHumidity_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "specific_humidity_120m", "RDPS_10km_SpecificHumidity_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "wind_speed_40m", "RDPS_10km_WindSpeed_40m", "available-not-stored", "WCS-only; production storage pending."),
    _sf("eccc-rdps", "wind_speed_80m", "RDPS_10km_WindSpeed_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "wind_speed_120m", "RDPS_10km_WindSpeed_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "wind_direction_40m", "RDPS_10km_WindDir_40m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "wind_direction_80m", "RDPS_10km_WindDir_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "wind_direction_120m", "RDPS_10km_WindDir_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-rdps", "relative_humidity_40m", None, "not-published",
        "RDPS publishes SpecificHumidity_40m and no RelativeHumidity_40m."),
    _sf("eccc-rdps", "seeing_class_eccc", "RDPS_10km_SeeingIndex", "available-not-stored",
        "The isolated WCS experiment retrieved and API-read this unlabelled class field. The "
        "production adapter remains Datamart GRIB and does not store it; class-zero semantics "
        "remain unresolved."),
    _sf("eccc-rdps", "transparency_class_eccc", "RDPS_10km_SkyTransparencyIndex", "available-not-stored",
        "The isolated WCS experiment retrieved and API-read this unlabelled class field. The "
        "production adapter remains Datamart GRIB and does not store it; class-zero semantics "
        "remain unresolved."),
    _sf("eccc-rdps", "radiative_surface_temperature", "RDPS_10km_RadiativeTemp", "available-not-stored",
        "'Aggregate surface radiative temperature'. Whether this is the same physical quantity "
        "as HRDPS SKINT is unverified, which is why they are separate keys."),
    _sf("eccc-rdps", "skin_temperature", None, "not-published",
        "No SKINT coverage exists for RDPS; RadiativeTemp is a different quantity."),
    _sf("eccc-rdps", "sea_ice_fraction", "RDPS_10km_SeaIceFraction", "available-not-stored", "Verified live WCS capability."),
    _sf("eccc-rdps", "boundary_layer_height", "RDPS_10km_PlanetaryBoundaryLayerHeight", "available-not-stored",
        "Verified live."),
    _sf("eccc-rdps", "precipitable_water", None, "not-published", "As HRDPS."),

    _sf("eccc-gdps", "total_cloud_opacity", "GDPS_15km_TotalCloudCover", "stored", "Verified live."),
    _sf("eccc-gdps", "relative_humidity_pressure", "GDPS_15km_RelativeHumidity_<n>mb", "stored",
        "GeoMet advertises 31 levels plus 2 m; production storage is limited to the Datamart "
        "adapter's declared subset. " + _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-gdps", "temperature_40m", "GDPS_15km_AirTemp_40m", "available-not-stored",
        "GeoMet advertises this WCS-only height field; production remains on Datamart GRIB."),
    _sf("eccc-gdps", "temperature_80m", "GDPS_15km_AirTemp_80m", "available-not-stored", "As 40 m."),
    _sf("eccc-gdps", "temperature_120m", "GDPS_15km_AirTemp_120m", "available-not-stored", "As 40 m."),
    _sf("eccc-gdps", "specific_humidity_40m", "GDPS_15km_SpecificHumidity_40m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "specific_humidity_80m", "GDPS_15km_SpecificHumidity_80m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "specific_humidity_120m", "GDPS_15km_SpecificHumidity_120m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "wind_speed_40m", "GDPS_15km_WindSpeed_40m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "wind_speed_80m", "GDPS_15km_WindSpeed_80m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "wind_speed_120m", "GDPS_15km_WindSpeed_120m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "wind_direction_40m", "GDPS_15km_WindDir_40m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "wind_direction_80m", "GDPS_15km_WindDir_80m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "wind_direction_120m", "GDPS_15km_WindDir_120m", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "boundary_layer_height", "GDPS_15km_PlanetaryBoundaryLayerHeight", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "radiative_surface_temperature", "GDPS_15km_RadiativeTemp", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "sea_ice_fraction", "GDPS_15km_SeaIceFraction", "available-not-stored", "As temperature_40m."),
    _sf("eccc-gdps", "precipitable_water", None, "not-published", "As HRDPS."),

    _sf("eccc-reps", "total_cloud_opacity", "REPS.MEM.ETA_NT.<member>", "stored",
        "Instantaneous per the producer's documentation, per member, already subset to the box."),
    _sf("eccc-reps", "wind_speed_10m", "REPS.MEM.ETA_WSPD.<member>", "stored",
        "Speed only on every member."),
    _sf("eccc-reps", "wind_direction_10m", None, "not-published",
        "REPS publishes wind speed and no components on any member, so member wind direction is "
        "not retrievable. The value stays null and nothing derives a direction from a speed."),
    _sf("eccc-reps", "temperature_2m", "REPS.MEM.ETA_TT.<member>", "stored",
        "One of the 22 ETA_* surface fields the GeoMet inventory lists per member, subset server "
        "side. Every published member field is stored under the every_published_field scope."),
    _sf("eccc-reps", "relative_humidity_2m", "REPS.MEM.ETA_HR.<member>", "stored",
        _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-reps", "specific_humidity_2m", "REPS.MEM.ETA_HU.<member>", "stored",
        "One of the 22 ETA_* surface fields per member."),
    _sf("eccc-reps", "downward_shortwave_accumulated", "REPS.MEM.ETA_N4.<member>", "stored",
        "Accumulated downward shortwave, as HRDPS _N4; the accumulation window is not stated in "
        "the WMS title for this family either."),
    _sf("eccc-reps", "mean_sea_level_pressure", "REPS.MEM.ETA_PN-SLP.<member>", "stored",
        "As HRDPS PN-SLP; published in Pa and normalized to hPa on ingest."),
    _sf("eccc-reps", "relative_humidity_pressure", "REPS.MEM.PRES_HR.<hPa>.<member>", "stored",
        "9 pressure levels per member. " + _ECCC_LIQUID, phase="liquid"),
    _sf("eccc-reps", "temperature_pressure", "REPS.MEM.PRES_TT.<hPa>.<member>", "stored",
        "9 pressure levels per member, the same PRES_* set as PRES_HR."),
    _sf("eccc-reps", "geopotential_height_pressure", "REPS.MEM.PRES_GZ.<hPa>.<member>", "stored",
        "9 pressure levels per member, the same PRES_* set as PRES_HR. The remaining ETA_* fields "
        "the inventory names without an exact coverage id (precipitation types, NTAT_EI) and the "
        "PRES_* 40/80/120 m height fields, whose exact coverage naming the research did not "
        "establish, are left uncatalogued rather than mapped under a guessed id; they surface as "
        "uncatalogued_upstream_field at ingest if retrieved."),

    _sf("eccc-geps", "total_cloud_opacity", "GEPS.DIAG.*_NT.<reduction>", "stored",
        "Provider reductions only (ERMEAN, ERSSTD, percentiles ERC0-ERC100, threshold "
        "probabilities ERGE*/PROB); no GEPS.MEM.* coverages exist to reduce here. Stored as "
        "issued and never recombined with a statistic computed over another member set. The "
        "catalogue has no key that expresses 'a reduction of total_cloud_opacity' distinctly "
        "from the retrieved value itself, so every reduction type lands under this one key and "
        "the reduction identity (ERMEAN vs ERC50 vs ...) travels only in the upstream name, not "
        "in a separate catalogue key."),
    _sf("eccc-geps", "temperature_2m", "GEPS.DIAG.3_TT.<reduction>", "stored",
        "Verified live: GEPS.DIAG.3_TT.ERC50 answered 200, 1 474 B at native 0.5 deg. As "
        "total_cloud_opacity above: one of the provider's own reduction set, stored as issued, "
        "with no catalogue key distinguishing which reduction a given value is."),

    # --- GFS: geometric cloud, mixed-phase humidity ------------------------
    _sf("noaa-gfs", "total_cloud_geometric", "TCDC:entire atmosphere", "stored",
        "Maximum-random overlap geometric fraction. Not the same quantity as ECCC NT."),
    _sf("noaa-gfs", "relative_humidity_2m", "RH:2 m above ground", "stored", _GFS_MIXED,
        phase="mixed"),
    _sf("noaa-gfs", "relative_humidity_pressure", "RH:<n> mb", "stored", _GFS_MIXED, phase="mixed"),
    _sf("noaa-gfs", "cloud_low", "LCDC:low cloud layer", "stored",
        "The producer's own stratum, geometric."),
    _sf("noaa-gfs", "cloud_middle", "MCDC:middle cloud layer", "stored", "As cloud_low."),
    _sf("noaa-gfs", "cloud_high", "HCDC:high cloud layer", "stored", "As cloud_low."),
    _sf("noaa-gfs", "precipitable_water", "PWAT:entire atmosphere", "stored",
        "The only precipitable-water path into the evidence box: no ECCC model publishes it. "
        "1 221 201 B on the wire for about 4.5 KB of box, a ratio of about 270 to 1."),
    _sf("noaa-gfs", "wind_u_pressure", "UGRD:<n> mb", "stored",
        "Stored at the jet levels (200, 300) and the steering levels (500, 700, 850)."),
    _sf("noaa-gfs", "wind_v_pressure", "VGRD:<n> mb", "stored", "As wind_u_pressure."),
    _sf("noaa-gfs", "omega_pressure", "VVEL:<n> mb", "stored",
        "Stored at the three steering levels for the computed-residual interpolation methods."),
    _sf("noaa-gfs", "temperature_pressure", "TMP:<n> mb", "stored",
        "Stored at the steering levels."),
    _sf("noaa-gfs", "precipitation_accumulation", "APCP:surface", "available-not-stored",
        "Published by GFS and deliberately not retrieved: ECCC's HRDPA/RDPA analyses are the "
        "precipitation path for this box."),
    _sf("noaa-gfs", "sea_surface_temperature", "TMP:surface", "available-not-stored",
        "Published in pgrb2 and not fetched; the ocean family is served from CIOPS-East and "
        "RIOPS."),
    _sf("noaa-gfs", "aerosol_optical_depth_550nm", "AOTK:entire atmosphere",
        "available-not-stored",
        "Published in pgrb2b and not fetched. It is the only uncredentialed AOD anywhere near "
        "the box and is a candidate for the transparency derivation, which is a scope decision "
        "and not made here."),
    _sf("noaa-gfs", "cloud_top_pressure", "PRES:cloud top", "available-not-stored",
        "One of the 349 pgrb2b records outside the catalogue's families."),

    # --- GEFS: family fields only, plus the six-hour mean cloud ------------
    _sf("noaa-gefs", "temperature_2m", "TMP:2 m above ground", "stored",
        "One of the seven family fields the ensemble-families change stores for GEFS under its "
        "family_fields_only scope."),
    _sf("noaa-gefs", "dew_point_2m", "DPT:2 m above ground", "stored", "Family field."),
    _sf("noaa-gefs", "relative_humidity_2m", "RH:2 m above ground", "stored", _GFS_MIXED,
        phase="mixed"),
    _sf("noaa-gefs", "wind_u_10m", "UGRD:10 m above ground", "stored", "Family field."),
    _sf("noaa-gefs", "wind_v_10m", "VGRD:10 m above ground", "stored", "Family field."),
    _sf("noaa-gefs", "mean_sea_level_pressure", "PRMSL:mean sea level", "stored",
        "Family field; published in Pa and normalized to hPa on ingest."),
    _sf("noaa-gefs", "total_cloud_mean_6h", "TCDC:entire atmosphere (n-n+6 hour ave fcst)",
        "stored",
        "Confirmed at the GRIB2 level, not only from the .idx label: 0-3 hour ave at f003, 0-6 at "
        "f006, 18-24 at f024, 378-384 at f384. Never instantaneous, at any lead, in any product "
        "set."),
    _sf("noaa-gefs", "total_cloud_geometric", "TCDC:475 mb", "available-not-stored",
        "The only instantaneous cloud records anywhere in GEFS are TCDC:475 mb (a single "
        "isobaric level, not a column), TCDC:convective cloud layer, HGT:cloud ceiling, "
        "CWAT:entire atmosphere and the convective cloud bottom/top pressures. None is a column "
        "cover, so GEFS gives no member-level instantaneous cloud column to draw beside HRDPS or "
        "GFS."),
    _sf("noaa-gefs", "cloud_low", "TCDC:low cloud layer (18-24 hour ave fcst)",
        "available-not-stored",
        "The layered cloud is averaged too, so it is not the instantaneous provider stratum "
        "cloud_low means. Catalogued rather than stored under a key that would misstate it."),
    _sf("noaa-gefs", "cloud_middle", "TCDC:middle cloud layer (18-24 hour ave fcst)",
        "available-not-stored", "As cloud_low."),
    _sf("noaa-gefs", "cloud_high", "TCDC:high cloud layer (18-24 hour ave fcst)",
        "available-not-stored", "As cloud_low."),
    _sf("noaa-gefs", "cloud_ceiling", "HGT:cloud ceiling", "available-not-stored",
        "Instantaneous and member-level, in pgrb2s at 0.25 deg; 1 029 967 B per record, about "
        "32 MB per lead across 31 members."),
    _sf("noaa-gefs", "relative_humidity_pressure", "RH:<n> mb", "available-not-stored",
        "10 pressure levels plus 2 m in pgrb2a and a further 21 levels plus 4 hybrid levels in "
        "pgrb2b, none fetched: GEFS cannot subset server side, so only the seven catalogue-family "
        "fields are stored (temperature_2m, dew_point_2m, relative_humidity_2m, wind_u_10m, "
        "wind_v_10m, mean_sea_level_pressure, total_cloud_mean_6h) and the pressure-level profile "
        "is outside that scope, not withheld for a storage quota."),

    # --- ECMWF -------------------------------------------------------------
    _sf("ecmwf-ifs", "total_cloud_geometric", "tcc", "stored",
        "Instantaneous, product definition template 4.1. Geometric, as GFS."),
    _sf("ecmwf-ifs", "temperature_2m", "2t", "stored", "Verified in the .index."),
    _sf("ecmwf-ifs", "dew_point_2m", "2d", "stored", "Verified in the .index."),
    _sf("ecmwf-ifs", "wind_u_10m", "10u", "stored", "Verified in the .index."),
    _sf("ecmwf-ifs", "wind_v_10m", "10v", "stored", "Verified in the .index."),
    _sf("ecmwf-ifs", "mean_sea_level_pressure", "msl", "stored", "Verified in the .index."),
    _sf("ecmwf-ifs", "precipitation_accumulation", "tp", "stored", "Verified in the .index."),
    _sf("ecmwf-ifs", "cloud_low", "lcc", "available-not-stored",
        "One of the 48 published parameters outside the fetched set; there is no server-side "
        "subsetting, so a record costs its whole file."),
    _sf("ecmwf-ifs", "cloud_middle", "mcc", "available-not-stored", "As lcc."),
    _sf("ecmwf-ifs", "cloud_high", "hcc", "available-not-stored", "As lcc."),
    _sf("ecmwf-ifs", "geopotential_height_pressure", "gh", "available-not-stored",
        "Published on the pl levels and not fetched."),
    _sf("ecmwf-ens", "total_cloud_geometric", "tcc", "stored",
        "Instantaneous per-member tcc, PDT 4.1. One of the six family fields IFS ENS stores under "
        "its family_fields_only scope; the other 47 published parameters are not fetched."),
    _sf("ecmwf-ens", "temperature_2m", "2t", "stored", "Family field."),
    _sf("ecmwf-ens", "dew_point_2m", "2d", "stored", "Family field."),
    _sf("ecmwf-ens", "wind_u_10m", "10u", "stored", "Family field."),
    _sf("ecmwf-ens", "wind_v_10m", "10v", "stored", "Family field."),
    _sf("ecmwf-ens", "mean_sea_level_pressure", "msl", "stored", "Family field."),
    _sf("ecmwf-ens", "cloud_low", "lcc", "not-published",
        "No layered cloud (lcc/mcc/hcc) exists in the IFS ENS open-data set; only whole-column "
        "tcc is published. Not a scope exclusion: the producer does not publish this field for "
        "this family."),
    _sf("ecmwf-ens", "cloud_middle", "mcc", "not-published", "As cloud_low."),
    _sf("ecmwf-ens", "cloud_high", "hcc", "not-published", "As cloud_low."),
    _sf("ecmwf-ens", "geopotential_height_pressure", "gh", "available-not-stored",
        "One of the 41 published parameters outside the six family fields; published on 14 "
        "pressure levels per member and not fetched under the family_fields_only scope."),
    _sf("ecmwf-aifs-single", "total_cloud_geometric", "tcc", "available-not-stored",
        "Published and not fetched."),
    _sf("ecmwf-aifs-ens", "total_cloud_geometric", "tcc", "stored",
        "Instantaneous per-member tcc, PDT 4.1 verified live. One of the nine family fields "
        "AIFS-ENS stores under its family_fields_only scope."),
    _sf("ecmwf-aifs-ens", "temperature_2m", "2t", "stored", "Family field."),
    _sf("ecmwf-aifs-ens", "dew_point_2m", "2d", "stored", "Family field."),
    _sf("ecmwf-aifs-ens", "wind_u_10m", "10u", "stored", "Family field."),
    _sf("ecmwf-aifs-ens", "wind_v_10m", "10v", "stored", "Family field."),
    _sf("ecmwf-aifs-ens", "mean_sea_level_pressure", "msl", "stored", "Family field."),
    _sf("ecmwf-aifs-ens", "cloud_low", "lcc", "stored",
        "The only catalogued family that publishes per-member low cloud; presence verified live, "
        "product definition template unverified."),
    _sf("ecmwf-aifs-ens", "cloud_middle", "mcc", "stored",
        "Presence verified live, product definition template unverified."),
    _sf("ecmwf-aifs-ens", "cloud_high", "hcc", "stored",
        "Presence verified live, product definition template unverified."),
    _sf("ecmwf-aifs-ens", "geopotential_height_pressure", "z", "available-not-stored",
        "One of the 20 published parameters outside the nine family fields; published on 14 "
        "pressure levels per member (AIFS-ENS names it z, not gh) and not fetched."),

    # --- ICON --------------------------------------------------------------
    _sf("dwd-icon-global", "total_cloud_geometric", "clct", "stored",
        "Geometric column cloud. No ICON run is published today: the feed is on its native "
        "icosahedral mesh and no regrid is invented here."),
    _sf("dwd-icon-global", "temperature_2m", "t_2m", "stored", "Mapped, pending the regrid."),
    _sf("dwd-icon-global", "relative_humidity_2m", "relhum_2m", "stored",
        "Mapped, pending the regrid. The saturation phase is not measured for ICON in this "
        "deployment, so no phase is declared and the field cannot be served until one is.",
        phase=None),
    _sf("dwd-icon-global", "wind_u_10m", "u_10m", "stored", "Mapped, pending the regrid."),
    _sf("dwd-icon-global", "wind_v_10m", "v_10m", "stored", "Mapped, pending the regrid."),
    _sf("dwd-icon-global", "mean_sea_level_pressure", "pmsl", "stored",
        "Mapped, pending the regrid."),
    _sf("dwd-icon-global", "precipitation_accumulation", "tot_prec", "stored",
        "Mapped, pending the regrid."),
    _sf("dwd-icon-global", "temperature_pressure", "t", "available-not-stored",
        "Published on 138 model levels as separate files; 1288 files per lead is 3.109 GB on the "
        "wire, so the multi-level expansions stay catalogued rather than fetched."),
    _sf("dwd-icon-global", "relative_humidity_pressure", "relhum", "available-not-stored",
        "Published on 18 levels and not fetched."),
    _sf("dwd-icon-global", "wind_u_pressure", "u", "available-not-stored",
        "Published on 138 levels and not fetched."),
    _sf("dwd-icon-global", "wind_v_pressure", "v", "available-not-stored",
        "Published on 138 levels and not fetched."),

    # --- observations ------------------------------------------------------
    _sf("awc-metar-speci", "total_cloud_okta", "sky cover oktas", "stored",
        "Summed from the reported layers in eighths. A point observation over CYYT."),
    _sf("awc-metar-speci", "relative_humidity_2m", "derived from temp and dewp", "stored",
        "Computed from the report's own temperature and dew point, over liquid water.",
        phase="liquid"),
    _sf("awc-taf", "total_cloud_okta", "sky cover oktas", "stored", "As the METAR adapter."),

    # --- satellite ---------------------------------------------------------
    _sf("noaa-goes-east", "cloud_mask_class", "ABI-L2-ACMF", "stored",
        "The clear-sky mask's own four-value scene class, regridded and preserved with its DQF."),
    _sf("noaa-goes-east", "cloud_probability", "ABI-L2-ACMF", "stored",
        "Derived from the mask's class confidence, as retrieved."),
    _sf("noaa-goes-east", "cloud_top_height", "ABI-L2-ACHAF", "stored",
        "NOAA Provisional maturity; the disclosure travels with every value."),
    _sf("noaa-goes-east", "cloud_fraction_layer_1", "ABI-L2-CCLF", "available-not-stored",
        "The layered cloud fraction product is published hourly at 10 km, about 2 MB per hour, "
        "and is not fetched yet."),
    _sf("noaa-goes-east", "cloud_fraction_layer_2", "ABI-L2-CCLF", "available-not-stored",
        "As layer 1."),
    _sf("noaa-goes-east", "cloud_fraction_layer_3", "ABI-L2-CCLF", "available-not-stored",
        "As layer 1."),
    _sf("noaa-goes-east", "cloud_fraction_layer_4", "ABI-L2-CCLF", "available-not-stored",
        "As layer 1."),
    _sf("noaa-goes-east", "cloud_fraction_layer_5", "ABI-L2-CCLF", "available-not-stored",
        "As layer 1."),
    _sf("noaa-goes-east", "precipitable_water", "ABI-L2-TPWF", "available-not-stored",
        "Total precipitable water, 6 granules an hour at 10 km, not fetched."),
    _sf("noaa-goes-east", "cloud_top_pressure", "ABI-L2-CTPF", "available-not-stored",
        "Published at 10 km and not fetched."),

    # --- space weather -----------------------------------------------------
    _sf("noaa-swpc-kp", "kp_index", "planetary_k_index", "stored", "3-hourly, as retrieved."),
    _sf("noaa-swpc-kp", "a_running", "a_running", "stored", "As retrieved beside Kp."),
    _sf("noaa-swpc-kp", "kp_status", "status", "stored",
        "Carried per value so an outlook is never read as an observation."),
    _sf("noaa-swpc-rtsw", "bz_gsm", "rtsw_mag_1m.json bz_gsm", "stored",
        "The feed interleaves SOLAR-1, ACE and IMAP by instant with an active flag that was set "
        "on none of the last 24 h of records, so a consumer must pick a spacecraft itself. The "
        "spacecraft identity is not stored today and that omission is now load-bearing."),
    _sf("noaa-swpc-rtsw", "bt", "rtsw_mag_1m.json bt", "stored", "As bz_gsm."),
    _sf("noaa-swpc-rtsw", "solar_wind_speed", "rtsw_wind_1m.json speed", "available-not-stored",
        "The plasma half of the coupling picture, published on the same cadence and not fetched."),
    _sf("noaa-swpc-rtsw", "solar_wind_density", "rtsw_wind_1m.json density",
        "available-not-stored", "As solar_wind_speed."),
    _sf("noaa-swpc-rtsw", "solar_wind_temperature", "rtsw_wind_1m.json temperature",
        "available-not-stored", "As solar_wind_speed."),
    _sf("noaa-swpc-ovation", "aurora_probability", "ovation_aurora_latest.json", "stored",
        "Sampled at the requested coordinate exactly as stored."),

    # --- ECCC point and grid products --------------------------------------
    _sf("eccc-radar", "radar_echo", "RADAR_1KM_RRAI + RADAR_1KM_RSNO", "stored",
        "The mosaic's own 'looked and saw nothing' arrives as value 0 and must be recognised by "
        "name, not by its number."),
    _sf("eccc-radar", "precipitation_rate", "RADAR_1KM_RRAI", "stored",
        "Declared to the manifest only when the scan carried a value."),
    _sf("eccc-radar", "snow_rate", "RADAR_1KM_RSNO", "stored", "As precipitation_rate."),
    _sf("eccc-lightning", "lightning_observed", "Lightning_2.5km_Density", "stored",
        "An interval with no flashes is a complete answer."),
    _sf("eccc-lightning", "lightning_strike", "Lightning_2.5km_Density", "stored",
        "Density in flash km-2 min-1, from the layer's own 'flash/km2/min'."),
    _sf("eccc-cap-alerts", "alerts_in_force", "Current-Alerts", "stored",
        "How many alerts cover the sampled point."),
    _sf("eccc-aqhi", "air_quality_health_index", "AQHI-OBS", "stored", "Station observations."),
    _sf("eccc-raqdps", "pm2_5_surface", "RAQDPS.SFC_PM2.5", "available-not-stored",
        "Hourly at 10 km, about 33 KB per step through GeoMet WCS; not retrieved yet."),
    _sf("eccc-raqdps", "pm2_5_column", "RAQDPS.EATM_PM2.5", "available-not-stored",
        "As pm2_5_surface. The aerosol term a transparency derivation would read."),
    _sf("eccc-raqdps", "aerosol_optical_depth_550nm", None, "not-published",
        "No aerosol optical depth of any kind exists on GeoMet: zero matches for aod, aerosol or "
        "optical across all 6123 coverage ids. ECCC publishes mass concentration, never optical "
        "depth."),
    _sf("copernicus-cams", "aerosol_optical_depth_550nm",
        "total_aerosol_optical_depth_550nm", "available-not-stored",
        "Published with 469, 670, 865 and 1240 nm and eight speciated 550 nm AODs, and "
        "credential-blocked: the ADS execute endpoint returns 401 anonymously."),

    # --- astronomy geometry ------------------------------------------------
    _sf("nasa-jpl-de442", "sun_altitude", "DE442", "stored",
        "Computed here from the pinned ephemeris by the registered geometry method; the class is "
        "derived_here and the method version travels with every value."),
    _sf("nasa-jpl-de442", "sun_azimuth", "DE442", "stored", "As sun_altitude."),
    _sf("nasa-jpl-de442", "moon_altitude", "DE442", "stored", "As sun_altitude."),
    _sf("nasa-jpl-de442", "moon_azimuth", "DE442", "stored", "As sun_altitude."),
    _sf("nasa-jpl-de442", "moon_phase_angle", "DE442", "stored", "As sun_altitude."),
    _sf("nasa-jpl-de442", "moon_illuminated_fraction", "DE442", "stored", "As sun_altitude."),
    _sf("nasa-jpl-de442", "moon_separation", "DE442", "stored", "As sun_altitude."),
    _sf("nasa-jpl-de442", "twilight_state", "DE442", "stored", "As sun_altitude."),

    # --- marine ------------------------------------------------------------
    _sf("eccc-ciops-east", "sea_surface_temperature", "SST", "available-not-stored",
        "Published at 2 km and not retrieved yet."),
    _sf("eccc-ciops-east", "current_u", "current_u", "available-not-stored", "As SST."),
    _sf("eccc-ciops-east", "current_v", "current_v", "available-not-stored", "As SST."),
    _sf("eccc-ciops-east", "salinity", "salinity", "available-not-stored", "As SST."),
    _sf("eccc-rdwps", "significant_wave_height", "significant_wave_height",
        "available-not-stored", "Published and not retrieved yet."),
    _sf("eccc-rdwps", "wind_wave_height", "wind_wave_height", "available-not-stored",
        "As significant_wave_height."),
    _sf("eccc-rdwps", "swell_height", "swell_height", "available-not-stored",
        "As significant_wave_height."),
    _sf("eccc-rdwps", "wave_direction", "wave_direction", "available-not-stored",
        "As significant_wave_height."),
    _sf("eccc-rdwps", "wave_period", "wave_period", "available-not-stored",
        "As significant_wave_height."),
    _sf("eccc-gdsps", "storm_surge", "storm_surge", "available-not-stored",
        "Published and not retrieved yet."),
]


# ---------------------------------------------------------------------------
# The materialized catalogue and its typed view.
# ---------------------------------------------------------------------------

def catalogue() -> dict[str, Any]:
    """The catalogue as plain JSON-able data, for the schema check and export."""
    return {
        "catalogue_version": CATALOGUE_VERSION,
        "as_of": AS_OF,
        "families": [dict(item) for item in FAMILIES],
        "fields": [dict(item) for item in FIELDS],
        "source_scope": [dict(item) for item in SOURCE_SCOPE],
        "source_fields": [dict(item) for item in SOURCE_FIELDS],
    }


@dataclass(frozen=True)
class Family:
    """A named group of related but non-identical quantities, and its note."""

    name: str
    title: str
    note: str
    groups: Mapping[str, str]


@dataclass(frozen=True)
class Field:
    """One physical quantity at one level with one unit and one declared phase."""

    key: str
    quantity: str
    units: str | None
    family: str
    level: str
    level_coordinate: str | None
    standard_name: str | None
    comparability_group: str
    evidence_classes: tuple[str, ...]
    phase_attribute: bool
    range: tuple[float, float] | None
    description: str

    @property
    def is_profile(self) -> bool:
        """True where the levels live on a coordinate rather than in the key."""
        return self.level_coordinate is not None

    def evidence_class_refused(self, name: str) -> bool:
        """True where this field may not carry that class at all.

        Sun altitude is never retrieved; a producer's own cloud cover is never
        derived here. Saying so per field is what stops a display construction
        being published under a key a reader reads as the producer's own.
        """
        return name not in self.evidence_classes


@dataclass(frozen=True)
class SourceField:
    """What one source does about one catalogue key."""

    source_id: str
    key: str
    upstream: str | None
    storage: str
    note: str
    phase: str | None = None

    @property
    def stored(self) -> bool:
        return self.storage == "stored"


@dataclass(frozen=True)
class SourceScope:
    """Whether a source's access path can subset, and what that costs."""

    source_id: str
    subsetting: str
    policy: str
    published_field_count: int | None
    counted_from: str | None
    note: str


@dataclass(frozen=True)
class Resolved:
    """A catalogue key plus, for a level-expanded name, the level it carried."""

    field: Field
    level: str | None = None

    @property
    def key(self) -> str:
        return self.field.key


@dataclass(frozen=True)
class Comparability:
    """Whether two served values may be put on one ramp, one axis or one difference."""

    comparable: bool
    reason: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"comparable": self.comparable, "reason": self.reason, "detail": self.detail}


def _build() -> tuple[dict[str, Field], dict[str, Family], list[tuple[Any, Field]]]:
    families = {
        item["name"]: Family(item["name"], item["title"], item["note"], dict(item.get("groups", {})))
        for item in FAMILIES
    }
    fields: dict[str, Field] = {}
    patterns: list[tuple[Any, Field]] = []
    for item in FIELDS:
        entry = Field(
            key=item["key"],
            quantity=item["quantity"],
            units=item["units"],
            family=item["family"],
            level=item["level"],
            level_coordinate=item.get("level_coordinate"),
            standard_name=item.get("standard_name"),
            comparability_group=item["comparability_group"],
            evidence_classes=tuple(item["evidence_classes"]),
            phase_attribute=bool(item.get("phase_attribute", False)),
            range=tuple(item["range"]) if item.get("range") else None,  # type: ignore[arg-type]
            description=item["description"],
        )
        fields[entry.key] = entry
        pattern = item.get("level_suffix_pattern")
        if pattern:
            patterns.append((re.compile(pattern), entry))
    return fields, families, patterns


_FIELDS, _FAMILIES, _LEVEL_PATTERNS = _build()

_SOURCE_FIELDS: tuple[SourceField, ...] = tuple(
    SourceField(
        source_id=item["source_id"],
        key=item["key"],
        upstream=item.get("upstream"),
        storage=item["storage"],
        note=item["note"],
        phase=item.get("phase"),
    )
    for item in SOURCE_FIELDS
)

_SOURCE_SCOPE: dict[str, SourceScope] = {
    item["source_id"]: SourceScope(
        source_id=item["source_id"],
        subsetting=item["subsetting"],
        policy=item["policy"],
        published_field_count=item.get("published_field_count"),
        counted_from=item.get("counted_from"),
        note=item["note"],
    )
    for item in SOURCE_SCOPE
}


# ---------------------------------------------------------------------------
# Query surface. Everything the API, the interface and ingest need is here;
# nothing outside this module should reach into the tables above.
# ---------------------------------------------------------------------------

def keys() -> tuple[str, ...]:
    """Every catalogue key, sorted."""
    return tuple(sorted(_FIELDS))


def has_field(key: str) -> bool:
    """True where ``key`` is a catalogue key, level-expanded names included."""
    try:
        resolve(key)
    except UnknownFieldKey:
        return False
    return True


def field(key: str) -> Field:
    """The field for a catalogue key. Raises rather than returning a placeholder."""
    try:
        return _FIELDS[key]
    except KeyError:
        raise UnknownFieldKey(key) from None


def resolve(name: str) -> Resolved:
    """Resolve an artifact variable name to its catalogue key and level.

    A plain key resolves to itself with no level. A level-expanded name that a
    GRIB adapter writes one variable per level for - ``relative_humidity_850hPa``
    - resolves to the one profile key and the level it carried, so the
    catalogue keeps its "one key with a level coordinate" shape without the
    retrieval having to change grid layout to match.
    """
    entry = _FIELDS.get(name)
    if entry is not None:
        return Resolved(entry)
    for pattern, profile in _LEVEL_PATTERNS:
        match = pattern.match(name)
        if match:
            return Resolved(profile, f"{match.group('level')} hPa")
    raise UnknownFieldKey(name)


def units_for(key: str) -> str | None:
    """The normalized unit a value under ``key`` must carry, or None where the
    producer declares it per artifact and no normalization pins it."""
    return resolve(key).field.units


def requires_phase(key: str) -> bool:
    """True where every value under this key must carry a liquid/mixed phase."""
    return resolve(key).field.phase_attribute


def family(name: str) -> Family:
    try:
        return _FAMILIES[name]
    except KeyError:
        raise UnknownFamily(name) from None


def families() -> tuple[Family, ...]:
    return tuple(_FAMILIES[name] for name in sorted(_FAMILIES))


def family_of(key: str) -> str:
    """The family this key belongs to. Every field belongs to exactly one."""
    return resolve(key).field.family


def members(family_name: str) -> tuple[str, ...]:
    """Every catalogue key in one family, sorted."""
    if family_name not in _FAMILIES:
        raise UnknownFamily(family_name)
    return tuple(sorted(key for key, entry in _FIELDS.items() if entry.family == family_name))


def comparability(
    key_a: str,
    key_b: str,
    *,
    phase_a: str | None = None,
    phase_b: str | None = None,
    temperature_k: float | None = None,
) -> Comparability:
    """Whether two values may be drawn on one ramp, one axis or one difference.

    Two fields are comparable only inside one family and one comparability
    group: that is what stops opacity-weighted and geometric cloud sharing a
    colour ramp. Above that sits the humidity rule: two relative humidities of
    different phase are not comparable whenever either value's air temperature
    is below 273.16 K, and are comparable above it, because that is where the
    two saturation definitions diverge.
    """
    left, right = resolve(key_a).field, resolve(key_b).field
    if left.family != right.family:
        return Comparability(
            False,
            "family",
            f"{left.key} is in the {left.family} family and {right.key} is in {right.family}; "
            "they do not measure related quantities at all",
        )
    group = family(left.family)
    if left.comparability_group != right.comparability_group:
        return Comparability(
            False,
            "definition",
            f"{left.key} is {group.groups.get(left.comparability_group, left.comparability_group)} "
            f"and {right.key} is {group.groups.get(right.comparability_group, right.comparability_group)}. "
            + group.note,
        )
    if left.phase_attribute and right.phase_attribute:
        if phase_a is None or phase_b is None:
            return Comparability(
                False,
                "phase_missing",
                "a humidity value without its phase cannot be compared: a threshold calibrated "
                "on one phase is not transferable to the other",
            )
        if phase_a != phase_b:
            if temperature_k is None:
                return Comparability(
                    False,
                    "phase",
                    f"{phase_a} and {phase_b} saturation bases diverge below {FREEZING_K} K and "
                    "no air temperature was supplied to say which side of it these values sit on",
                )
            if temperature_k < FREEZING_K:
                return Comparability(
                    False,
                    "phase",
                    f"a {phase_a}-basis and a {phase_b}-basis relative humidity differ by up to "
                    f"about 24 percent for identical air below {FREEZING_K} K, and this pair is "
                    f"at {temperature_k:.2f} K",
                )
    return Comparability(True)


def source_mapping(source_id: str) -> tuple[SourceField, ...]:
    """Everything the catalogue records about one source's fields."""
    return tuple(item for item in _SOURCE_FIELDS if item.source_id == source_id)


def source_scope(source_id: str) -> SourceScope | None:
    """Whether this source's access path subsets, and what that costs."""
    return _SOURCE_SCOPE.get(source_id)


def mapped_sources() -> tuple[str, ...]:
    return tuple(sorted({item.source_id for item in _SOURCE_FIELDS}))


def storage_of(source_id: str, key: str) -> str | None:
    """What this source does about this key, or None where it says nothing."""
    resolved = resolve(key).key
    for item in _SOURCE_FIELDS:
        if item.source_id == source_id and item.key == resolved:
            return item.storage
    return None


def phase_of(source_id: str, key: str) -> str | None:
    """The saturation phase this source's humidity is defined over, if declared."""
    resolved = resolve(key).key
    for item in _SOURCE_FIELDS:
        if item.source_id == source_id and item.key == resolved:
            return item.phase
    return None


def key_for_upstream(source_id: str, upstream: str) -> str | None:
    """The catalogue key one source's own name for a quantity maps to.

    A producer names its fields its own way - a WCS coverage id, a GRIB record
    label, a JSON member - and several of those are templates over a level or a
    member (``HRDPS.CONTINENTAL.PRES_HR.<hPa>``). A template matches any name
    that starts with the literal text before its first placeholder, which is
    what lets one mapping entry cover 28 pressure-level coverages without
    listing them. Returns None where this source claims no such name, which is
    what makes a newly advertised upstream field visible instead of silent.
    """
    mine = [item for item in _SOURCE_FIELDS if item.source_id == source_id and item.upstream]
    for item in mine:  # an exact name always beats a template that merely covers it
        if item.upstream == upstream:
            return item.key
    for item in mine:
        template = item.upstream or ""
        head, marker, _ = template.partition("<")
        if marker and head and upstream.startswith(head):
            return item.key
    return None


def available_not_stored(source_id: str | None = None) -> tuple[SourceField, ...]:
    """Fields a producer publishes that this deployment does not store.

    Distinct from "not retrieved" and from "blocked": the field exists upstream,
    the catalogue knows it, and the reader is told it is not kept here.
    """
    return tuple(
        item
        for item in _SOURCE_FIELDS
        if item.storage == "available-not-stored" and (source_id is None or item.source_id == source_id)
    )


def not_published(source_id: str | None = None) -> tuple[SourceField, ...]:
    """Gaps a producer leaves: the value stays null and nothing derives one."""
    return tuple(
        item
        for item in _SOURCE_FIELDS
        if item.storage == "not-published" and (source_id is None or item.source_id == source_id)
    )


# ---------------------------------------------------------------------------
# Self-check. Called by registry/audit.py; kept here so the catalogue's
# invariants live beside the catalogue rather than in the auditor.
# ---------------------------------------------------------------------------

def validate_catalogue(*, adapter_keys: Iterable[str] = ()) -> list[str]:
    """Every way the catalogue can be internally wrong, as a list of messages.

    ``adapter_keys`` is every key the adapter manifests declare today; each one
    must resolve, or an adapter is not schedulable.
    """
    errors: list[str] = []

    seen: set[str] = set()
    for entry in FIELDS:
        key = entry["key"]
        if key in seen:
            errors.append(f"duplicate field key: {key}")
        seen.add(key)
        if entry["family"] not in _FAMILIES:
            errors.append(f"{key}: unknown family {entry['family']!r}")
            continue
        group = _FAMILIES[entry["family"]].groups
        if group and entry["comparability_group"] not in group:
            errors.append(
                f"{key}: comparability group {entry['comparability_group']!r} is not declared by "
                f"the {entry['family']} family"
            )
        for name in entry["evidence_classes"]:
            if name not in EVIDENCE_CLASSES:
                errors.append(f"{key}: {name!r} is not one of the six evidence classes")
        if entry["units"] is None and "provider" not in entry["description"].lower():
            errors.append(
                f"{key}: declares no unit and gives no reason; a null unit switches the manifest "
                "unit check off and must say why"
            )
        if entry.get("level_coordinate") and not entry.get("level_suffix_pattern"):
            errors.append(
                f"{key}: is a profile field with no level_suffix_pattern, so the level-expanded "
                "variables the GRIB adapters write could never resolve to it"
            )
        if entry.get("level_suffix_pattern") and not entry.get("level_coordinate"):
            errors.append(f"{key}: declares a level suffix pattern but no level coordinate")

    # A family with one member carries no comparability decision and is a sign
    # the split was never finished; a family with no member is dead weight.
    for name in _FAMILIES:
        if not members(name):
            errors.append(f"family {name} has no members")

    # Height fields must carry their level in the key, and pressure-level
    # fields must not: that is the level convention, checked rather than
    # trusted.
    for key, entry in _FIELDS.items():
        if re.search(r"_\d+hPa$", key):
            errors.append(
                f"{key}: a pressure level belongs on a coordinate, not in the key; declare one "
                "profile field with a level_suffix_pattern instead"
            )
        if entry.level_coordinate is None and re.search(r"\b(\d+) (m|hPa)\b", entry.level):
            suffix = re.search(r"\b(\d+) (m|hPa)\b", entry.level)
            assert suffix is not None
            expected = f"_{suffix.group(1)}{suffix.group(2)}"
            if not key.endswith(expected):
                errors.append(
                    f"{key}: is at {entry.level} and does not carry the level in its key "
                    f"(expected the suffix {expected})"
                )

    known_sources = {item["source_id"] for item in SOURCE_SCOPE}
    for item in SOURCE_FIELDS:
        if item["key"] not in _FIELDS:
            errors.append(
                f"{item['source_id']}: maps {item['key']!r}, which the catalogue does not carry"
            )
        if item["storage"] not in STORAGE_STATES:
            errors.append(f"{item['source_id']}/{item['key']}: unknown storage {item['storage']!r}")
        if item.get("phase") and item["key"] in _FIELDS and not _FIELDS[item["key"]].phase_attribute:
            errors.append(
                f"{item['source_id']}/{item['key']}: declares a phase for a field that has none"
            )
    pairs = [(item["source_id"], item["key"]) for item in SOURCE_FIELDS]
    for pair in sorted({pair for pair in pairs if pairs.count(pair) > 1}):
        errors.append(f"{pair[0]}: maps {pair[1]!r} more than once")

    # Every source that cannot subset must say so, so that a field it does not
    # store is recorded as available-not-stored rather than quietly missing.
    for source_id in sorted({item["source_id"] for item in SOURCE_FIELDS}):
        scope = _SOURCE_SCOPE.get(source_id)
        if scope is None:
            continue
        if scope.policy == "family_fields_only" and not available_not_stored(source_id):
            errors.append(
                f"{source_id}: stores only the family fields and records nothing as "
                "available-not-stored, so a reader cannot see what the producer publishes"
            )
    scope_by_id = {item["source_id"]: item for item in SOURCE_SCOPE}
    for source_id in sorted(known_sources - {item["source_id"] for item in SOURCE_FIELDS}):
        # A source honestly declaring zero measured published fields (ICON-EPS: nothing about
        # it was measured on ticket 22) maps no field by construction, which is a different
        # statement from a source that was measured and simply never wired up.
        if scope_by_id[source_id].get("published_field_count") == 0:
            continue
        errors.append(f"{source_id}: declares a scope and maps no field")

    for key in sorted(set(adapter_keys)):
        try:
            resolve(key)
        except UnknownFieldKey:
            errors.append(f"adapter manifest declares {key!r}, which the catalogue does not carry")

    return errors
