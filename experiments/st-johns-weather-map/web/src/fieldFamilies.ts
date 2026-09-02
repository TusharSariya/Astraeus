// GENERATED FILE — do not edit by hand.
//
// Written by `web/scripts/generate-field-families.mjs` from the field
// catalogue in `registry/fields.py` and the shape in
// `registry/fields.schema.json`. Regenerate with:
//
//     cd web && node scripts/generate-field-families.mjs
//
// `src/field-family-catalogue.test.ts` fails when this file is stale.
//
// This is DISPLAY METADATA ONLY: a family's title and note, a member's
// definition. A served value's family always comes from the response's own
// `family`; nothing here is ever used to guess one from a key's spelling.

export interface CatalogueFamilyCopy {
  name: string
  title: string
  note: string
  /** The comparability groups inside the family: the definitions that decide
   *  whether two members may share a ramp, an axis or a difference. */
  groups: Record<string, string>
}

export interface CatalogueFieldCopy {
  key: string
  family: string
  quantity: string
  units: string
  level: string | null
  comparabilityGroup: string | null
  description: string
}

export interface FieldCatalogueCopy {
  version: string
  asOf: string
  /** sha256 over the copied subset and the schema; the staleness test's hinge. */
  fingerprint: string
  families: CatalogueFamilyCopy[]
  fields: CatalogueFieldCopy[]
}

export const FIELD_CATALOGUE_COPY: FieldCatalogueCopy = {
  "version": "1.0.0",
  "asOf": "2026-09-02",
  "fingerprint": "49948dc61e3f1a0c296c1760dd4cf623f201c19c72fdee7db57ee03d5e23daf3",
  "families": [
    {
      "name": "air_quality",
      "title": "Air quality and aerosol",
      "note": "Particulate mass and aerosol optical depth are not the same quantity and no conversion between them is a measurement. Mass carries no wavelength dependence and no hygroscopic growth; a mass-to-extinction conversion is a citable method and must be declared derived-here. A surface concentration and a column burden are also not comparable. The health index is a categorical scale, not a concentration.",
      "groups": {
        "column_mass": "Mass burden integrated over the whole column.",
        "health_index": "A categorical public-health index.",
        "optical_depth": "Aerosol optical depth at a stated wavelength.",
        "surface_mass": "Mass concentration at the surface."
      }
    },
    {
      "name": "astronomy_geometry",
      "title": "Sun and Moon geometry",
      "note": "Positions and phases computed here from the pinned JPL DE442 ephemeris by a registered geometry method. Every member is derived-here: no producer publishes these for this site, and they are never presented as producer output. They are comparable with each other only in the trivial sense of sharing one ephemeris and one method version, which travel with every value.",
      "groups": {
        "altitude": "Geometric altitude above the horizon, unrefracted unless stated.",
        "azimuth": "Bearing east of true north.",
        "phase": "Illumination geometry of the Moon.",
        "separation": "Angular separation between two bodies.",
        "twilight": "Categorical twilight state from the Sun's altitude."
      }
    },
    {
      "name": "boundary_layer",
      "title": "Boundary layer",
      "note": "Boundary-layer depth diagnostics. Each producer diagnoses the top by its own criterion, so values are comparable only within one producer's definition.",
      "groups": {
        "depth": "Diagnosed planetary boundary layer height above ground."
      }
    },
    {
      "name": "cloud_cover",
      "title": "Cloud cover",
      "note": "Members measure how much sky is covered, by four incompatible definitions. Opacity-weighted cover (ECCC GEM 'NT') weights each layer by how much light it actually stops, so thin cirrus reads near zero. Geometric cover (GFS, ECMWF, ICON) is a maximum-random overlap of layer fractions and counts thin cirrus in full. A six-hour mean (GEFS) is a time average and is never an instant. Observed dome cover (METAR oktas) is one observer's fraction of the celestial dome at one point. Satellite layered fraction (GOES ABI Cloud Cover Layers) is a retrieval per vertical layer. Values from different definitions must never share a colour ramp, an axis or a difference view.",
      "groups": {
        "derived_repair": "A derived-here repair of a producer's column cover; never the producer's value.",
        "geometric_column": "Geometric maximum-random overlap whole-column fraction, instantaneous.",
        "observed_dome": "An observer's fraction of the celestial dome, reported in eighths.",
        "observed_layer": "An observer's reported cover for one reported cloud layer.",
        "opacity_weighted_column": "Opacity-weighted whole-column cover, instantaneous.",
        "provider_stratum": "The producer's own low/middle/high layer fraction, geometric.",
        "satellite_layer": "Satellite-retrieved fraction in one vertical layer of a layered product.",
        "scene_class": "A categorical clear/cloudy scene classification, not a fraction.",
        "time_mean_column": "Column cover averaged over a stated window, never an instant."
      }
    },
    {
      "name": "cloud_geometry",
      "title": "Cloud geometry",
      "note": "Heights and pressures of cloud boundaries. A satellite cloud-top height is a radiative retrieval of the highest opaque surface; an observer's layer base is the height a human judged a base to be at over one station. They answer different questions and are not comparable.",
      "groups": {
        "observed_base": "Observer-reported base of one reported layer, above ground.",
        "satellite_top": "Radiatively retrieved cloud-top height or pressure."
      }
    },
    {
      "name": "hazard",
      "title": "Hazards in force",
      "note": "Counts and categories of issued warnings. Never a physical quantity.",
      "groups": {
        "alert_count": "Number of alerts in force over the sampled area."
      }
    },
    {
      "name": "humidity",
      "title": "Humidity",
      "note": "Relative humidity, specific humidity, dew point and column water vapour. Relative humidity carries a required phase attribute: HRDPS and RDPS divide by saturation over liquid water at every temperature, GFS by a mixed-phase saturation ramping from ice at 253.16 K to water at 273.16 K. The two agree above freezing and differ by up to about 24 percent below it, so a liquid-versus-mixed pair is flagged not comparable whenever either value's air temperature is below 273.16 K. Specific humidity, dew point and precipitable water carry no phase ambiguity and are separate quantities, not relative humidity in other clothes.",
      "groups": {
        "column_vapour": "Vertically integrated water vapour over the whole column.",
        "dew_point": "Dew-point temperature.",
        "relative": "Relative humidity, phase-dependent below freezing.",
        "specific": "Mass of water vapour per mass of moist air."
      }
    },
    {
      "name": "lightning",
      "title": "Lightning",
      "note": "A detection flag and a flash density over a stated interval. An interval with no flashes is a complete answer, not a gap.",
      "groups": {
        "density": "Flash density over the producer's own interval.",
        "detection": "Whether any flash was detected in the interval."
      }
    },
    {
      "name": "marine",
      "title": "Marine",
      "note": "Sea state, sea surface temperature, currents, ice and surge. A significant wave height that combines wind wave and swell is not comparable with either partition alone. A modelled sea surface temperature and a satellite skin SST are different measurements of a stratified surface.",
      "groups": {
        "current": "Horizontal sea-water velocity component.",
        "ice": "Fraction of the cell covered by sea ice.",
        "salinity": "Sea-water salinity.",
        "sea_surface_temperature": "Temperature of the sea surface layer.",
        "surge": "Water level departure attributable to meteorological forcing.",
        "wave_direction": "Mean direction of the sea state.",
        "wave_height": "Height statistic of the combined sea state.",
        "wave_partition": "Height of one partition of the sea state.",
        "wave_period": "Mean or peak period of the sea state."
      }
    },
    {
      "name": "precipitation",
      "title": "Precipitation",
      "note": "An accumulation over a stated interval, an instantaneous rate and a radar echo flag are three different quantities. An accumulation over one hour and one over three hours are not comparable without the interval, which travels with the value.",
      "groups": {
        "accumulation": "Depth accumulated over the producer's own stated interval.",
        "echo": "Radar detection flag; its zero means 'looked and saw nothing'.",
        "rate": "Instantaneous precipitation rate.",
        "type": "Categorical precipitation type."
      }
    },
    {
      "name": "pressure",
      "title": "Pressure and geopotential",
      "note": "Mean sea level pressure is reduced to sea level by the producer's own reduction; surface pressure is the pressure at the model's own orography. They differ by the station's elevation and are not comparable.",
      "groups": {
        "geopotential": "Geopotential height of a pressure surface.",
        "mean_sea_level": "Pressure reduced to mean sea level by the producer.",
        "surface": "Pressure at the producer's own surface height."
      }
    },
    {
      "name": "radiation",
      "title": "Surface radiation",
      "note": "Every ECCC global-radiation coverage is an accumulation in J/m2 over a window the producer does not state in its title. Differencing consecutive steps for a mean flux would be derived-here, so an accumulation and a flux are separate keys and are not comparable.",
      "groups": {
        "accumulated": "Accumulated radiant energy over the producer's own window.",
        "flux": "Instantaneous radiant flux density."
      }
    },
    {
      "name": "seeing",
      "title": "Astronomical seeing",
      "note": "ECCC's RDPS seeing index is an unlabelled integer class 0-5 on the same footing as its transparency index. A derived-here arcsecond estimate from a Cn2 parameterisation is a physical angle. They are not comparable, and there is no seeing monitor, DIMM or Cn2 profiler anywhere near the evidence box, so a derived seeing field can be compared with ECCC's index and never validated against a measurement.",
      "groups": {
        "angular": "Angular full width at half maximum of a stellar image.",
        "class_index": "An unlabelled producer class index; the class definitions are not published."
      }
    },
    {
      "name": "space_weather",
      "title": "Space weather",
      "note": "Geomagnetic indices, solar-wind conditions at L1 and an aurora probability. The planetary indices are different instruments on different cadences: Kp is 3-hourly, Hp30 half-hourly, Hp60 hourly, Dst hourly and none is a resampling of another. Solar-wind values at L1 have not yet reached the magnetosphere; a propagated value and an L1 value are not the same instant and are not comparable. The RTSW feed interleaves three spacecraft (SOLAR-1, ACE, IMAP) with no active flag set, so a value without a spacecraft identity cannot be weighed.",
      "groups": {
        "aurora_probability": "Modelled probability of visible aurora over a grid cell.",
        "imf": "Interplanetary magnetic field at the measuring spacecraft.",
        "planetary_index": "A planetary geomagnetic activity index on the producer's own cadence.",
        "ring_current_index": "A ring-current index in nanotesla.",
        "solar_wind_plasma": "Solar-wind plasma bulk properties at the measuring spacecraft.",
        "xray_flux": "Solar soft X-ray flux in a stated passband."
      }
    },
    {
      "name": "temperature",
      "title": "Temperature",
      "note": "Air temperature at a stated level, plus surface temperatures that are not air temperature at all. A screen temperature and a skin or radiative surface temperature are different quantities and are not comparable; whether ECCC's 'aggregate land surface skin temperature' and 'aggregate surface radiative temperature' are the same quantity is unverified and they are kept apart.",
      "groups": {
        "air": "Air temperature at a stated height or pressure level.",
        "radiative": "Aggregate surface radiative temperature; not verified equal to skin.",
        "skin": "Aggregate land surface skin temperature."
      }
    },
    {
      "name": "terrain",
      "title": "Terrain",
      "note": "Static model geometry. Not a forecast and not comparable with any of it.",
      "groups": {
        "orography": "The model's own surface height above the geoid."
      }
    },
    {
      "name": "transparency",
      "title": "Sky transparency",
      "note": "Four incompatible encodings of 'how clear the sky is'. ECCC's RDPS sky transparency index is an unlabelled integer class 0-4 whose class definitions could not be verified from any machine-readable source, and whose 0 may be a class or a not-computed sentinel; naked-eye limiting magnitude is a magnitude; extinction is magnitudes per air mass; and Clear Sky Chart's encoding is column water vapour, which is a moisture quantity and is served under precipitable_water in the humidity family, never as a transparency. No two of these are comparable, and none is convertible into another without a declared derivation.",
      "groups": {
        "class_index": "An unlabelled producer class index; the class definitions are not published.",
        "extinction": "Atmospheric extinction in magnitudes per air mass.",
        "limiting_magnitude": "Faintest naked-eye stellar magnitude at the zenith."
      }
    },
    {
      "name": "vertical_motion",
      "title": "Vertical motion",
      "note": "Pressure-coordinate vertical velocity. Positive omega is descent.",
      "groups": {
        "omega": "Vertical velocity in pressure coordinates."
      }
    },
    {
      "name": "visibility",
      "title": "Visibility and fog",
      "note": "Horizontal visibility, and the fog states read from it. An observed prevailing visibility is a human or instrument reading at one station; a model visibility is a diagnosis on a grid cell. A fog state derived here from present-weather codes is a derived-here classification and is never the producer's own observation.",
      "groups": {
        "derived_state": "A derived-here fog classification.",
        "horizontal": "Prevailing horizontal visibility.",
        "present_weather_flag": "A flag read out of the coded present-weather group."
      }
    },
    {
      "name": "wind",
      "title": "Wind",
      "note": "Wind as components and wind as speed and direction are the same vector in two encodings and are comparable within an encoding. A source stores what it publishes: GeoMet publishes speed and direction and no components anywhere, GRIB feeds publish components. Speed and direction reconstructed from components are derived-here and are served beside the raw values, never in place of them. Where a producer publishes speed only (REPS), direction stays null and nothing derives one.",
      "groups": {
        "component": "Grid-relative u and v components of the horizontal wind.",
        "direction": "Bearing the wind comes from, meteorological convention.",
        "gust": "Peak gust over the producer's own reporting interval.",
        "speed": "Scalar horizontal wind speed."
      }
    }
  ],
  "fields": [
    {
      "key": "a_running",
      "family": "space_weather",
      "quantity": "running a index",
      "units": "1",
      "level": "planetary",
      "comparabilityGroup": "planetary_index",
      "description": "The running a index as retrieved beside Kp."
    },
    {
      "key": "aerosol_optical_depth_550nm",
      "family": "air_quality",
      "quantity": "aerosol optical depth at 550 nm",
      "units": "1",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "optical_depth",
      "description": "Column aerosol optical depth at 550 nm. Not particulate mass: it carries wavelength dependence and hygroscopic growth that mass does not, so no conversion between them is a measurement. Every AOD path into the evidence box is credential-blocked today."
    },
    {
      "key": "air_quality_health_index",
      "family": "air_quality",
      "quantity": "air quality health index",
      "units": "index",
      "level": "station",
      "comparabilityGroup": "health_index",
      "description": "ECCC's categorical Air Quality Health Index. A scale, not a concentration."
    },
    {
      "key": "alerts_in_force",
      "family": "hazard",
      "quantity": "alerts in force",
      "units": "count",
      "level": "surface",
      "comparabilityGroup": "alert_count",
      "description": "How many ECCC public alerts cover the sampled point at the sampled instant."
    },
    {
      "key": "aurora_probability",
      "family": "space_weather",
      "quantity": "aurora visibility probability",
      "units": "percent",
      "level": "surface",
      "comparabilityGroup": "aurora_probability",
      "description": "SWPC OVATION modelled probability of visible aurora over a grid cell, sampled as stored. The one genuinely gridded space-weather product."
    },
    {
      "key": "boundary_layer_height",
      "family": "boundary_layer",
      "quantity": "planetary boundary layer height",
      "units": "m",
      "level": "surface",
      "comparabilityGroup": "depth",
      "description": "Diagnosed depth of the planetary boundary layer above ground (HRDPS _HPBL)."
    },
    {
      "key": "bt",
      "family": "space_weather",
      "quantity": "interplanetary magnetic field magnitude",
      "units": "nT",
      "level": "measuring spacecraft at L1",
      "comparabilityGroup": "imf",
      "description": "Total IMF magnitude at the measuring spacecraft."
    },
    {
      "key": "bz_gsm",
      "family": "space_weather",
      "quantity": "interplanetary magnetic field Bz, GSM",
      "units": "nT",
      "level": "measuring spacecraft at L1",
      "comparabilityGroup": "imf",
      "description": "Southward IMF component in GSM coordinates. The RTSW feed interleaves SOLAR-1, ACE and IMAP with no active flag set, so the measuring spacecraft's identity has to travel with the value."
    },
    {
      "key": "cloud_ceiling",
      "family": "cloud_geometry",
      "quantity": "cloud ceiling height",
      "units": "m",
      "level": "ceiling",
      "comparabilityGroup": "observed_base",
      "description": "Height above ground of the lowest broken or overcast layer."
    },
    {
      "key": "cloud_fraction_layer_1",
      "family": "cloud_cover",
      "quantity": "layered cloud fraction",
      "units": "percent",
      "level": "product layer 1 (lowest)",
      "comparabilityGroup": "satellite_layer",
      "description": "Cloud fraction in the lowest of the five vertical layers of the GOES ABI Cloud Cover Layers product. The layer boundaries are the product's own and were not verified in this deployment's research, so they travel with the value rather than being restated here."
    },
    {
      "key": "cloud_fraction_layer_2",
      "family": "cloud_cover",
      "quantity": "layered cloud fraction",
      "units": "percent",
      "level": "product layer 2",
      "comparabilityGroup": "satellite_layer",
      "description": "Cloud fraction in the second of the five GOES ABI Cloud Cover Layers layers."
    },
    {
      "key": "cloud_fraction_layer_3",
      "family": "cloud_cover",
      "quantity": "layered cloud fraction",
      "units": "percent",
      "level": "product layer 3",
      "comparabilityGroup": "satellite_layer",
      "description": "Cloud fraction in the third of the five GOES ABI Cloud Cover Layers layers."
    },
    {
      "key": "cloud_fraction_layer_4",
      "family": "cloud_cover",
      "quantity": "layered cloud fraction",
      "units": "percent",
      "level": "product layer 4",
      "comparabilityGroup": "satellite_layer",
      "description": "Cloud fraction in the fourth of the five GOES ABI Cloud Cover Layers layers."
    },
    {
      "key": "cloud_fraction_layer_5",
      "family": "cloud_cover",
      "quantity": "layered cloud fraction",
      "units": "percent",
      "level": "product layer 5 (highest)",
      "comparabilityGroup": "satellite_layer",
      "description": "Cloud fraction in the highest of the five GOES ABI Cloud Cover Layers layers."
    },
    {
      "key": "cloud_high",
      "family": "cloud_cover",
      "quantity": "high cloud cover",
      "units": "percent",
      "level": "high cloud layer",
      "comparabilityGroup": "provider_stratum",
      "description": "The producer's own high-cloud layer fraction (GFS HCDC)."
    },
    {
      "key": "cloud_layer_1_base",
      "family": "cloud_geometry",
      "quantity": "reported layer base height",
      "units": "m",
      "level": "reported cloud layer 1",
      "comparabilityGroup": "observed_base",
      "description": "Height above ground of the 1th reported layer's base."
    },
    {
      "key": "cloud_layer_1_cover",
      "family": "cloud_cover",
      "quantity": "reported layer cover",
      "units": "percent",
      "level": "reported cloud layer 1",
      "comparabilityGroup": "observed_layer",
      "description": "The 1th reported layer's cover as a percentage of the dome."
    },
    {
      "key": "cloud_layer_1_cover_code",
      "family": "cloud_cover",
      "quantity": "reported layer cover code",
      "units": "code",
      "level": "reported cloud layer 1",
      "comparabilityGroup": "observed_layer",
      "description": "The coded sky cover (SKC/FEW/SCT/BKN/OVC/VV) of the 1th layer the report lists, in the producer's own order. Never folded into low/middle/high strata: that would be a classification the owner has not approved."
    },
    {
      "key": "cloud_layer_2_base",
      "family": "cloud_geometry",
      "quantity": "reported layer base height",
      "units": "m",
      "level": "reported cloud layer 2",
      "comparabilityGroup": "observed_base",
      "description": "Height above ground of the 2th reported layer's base."
    },
    {
      "key": "cloud_layer_2_cover",
      "family": "cloud_cover",
      "quantity": "reported layer cover",
      "units": "percent",
      "level": "reported cloud layer 2",
      "comparabilityGroup": "observed_layer",
      "description": "The 2th reported layer's cover as a percentage of the dome."
    },
    {
      "key": "cloud_layer_2_cover_code",
      "family": "cloud_cover",
      "quantity": "reported layer cover code",
      "units": "code",
      "level": "reported cloud layer 2",
      "comparabilityGroup": "observed_layer",
      "description": "The coded sky cover (SKC/FEW/SCT/BKN/OVC/VV) of the 2th layer the report lists, in the producer's own order. Never folded into low/middle/high strata: that would be a classification the owner has not approved."
    },
    {
      "key": "cloud_layer_3_base",
      "family": "cloud_geometry",
      "quantity": "reported layer base height",
      "units": "m",
      "level": "reported cloud layer 3",
      "comparabilityGroup": "observed_base",
      "description": "Height above ground of the 3th reported layer's base."
    },
    {
      "key": "cloud_layer_3_cover",
      "family": "cloud_cover",
      "quantity": "reported layer cover",
      "units": "percent",
      "level": "reported cloud layer 3",
      "comparabilityGroup": "observed_layer",
      "description": "The 3th reported layer's cover as a percentage of the dome."
    },
    {
      "key": "cloud_layer_3_cover_code",
      "family": "cloud_cover",
      "quantity": "reported layer cover code",
      "units": "code",
      "level": "reported cloud layer 3",
      "comparabilityGroup": "observed_layer",
      "description": "The coded sky cover (SKC/FEW/SCT/BKN/OVC/VV) of the 3th layer the report lists, in the producer's own order. Never folded into low/middle/high strata: that would be a classification the owner has not approved."
    },
    {
      "key": "cloud_layer_4_base",
      "family": "cloud_geometry",
      "quantity": "reported layer base height",
      "units": "m",
      "level": "reported cloud layer 4",
      "comparabilityGroup": "observed_base",
      "description": "Height above ground of the 4th reported layer's base."
    },
    {
      "key": "cloud_layer_4_cover",
      "family": "cloud_cover",
      "quantity": "reported layer cover",
      "units": "percent",
      "level": "reported cloud layer 4",
      "comparabilityGroup": "observed_layer",
      "description": "The 4th reported layer's cover as a percentage of the dome."
    },
    {
      "key": "cloud_layer_4_cover_code",
      "family": "cloud_cover",
      "quantity": "reported layer cover code",
      "units": "code",
      "level": "reported cloud layer 4",
      "comparabilityGroup": "observed_layer",
      "description": "The coded sky cover (SKC/FEW/SCT/BKN/OVC/VV) of the 4th layer the report lists, in the producer's own order. Never folded into low/middle/high strata: that would be a classification the owner has not approved."
    },
    {
      "key": "cloud_layer_5_base",
      "family": "cloud_geometry",
      "quantity": "reported layer base height",
      "units": "m",
      "level": "reported cloud layer 5",
      "comparabilityGroup": "observed_base",
      "description": "Height above ground of the 5th reported layer's base."
    },
    {
      "key": "cloud_layer_5_cover",
      "family": "cloud_cover",
      "quantity": "reported layer cover",
      "units": "percent",
      "level": "reported cloud layer 5",
      "comparabilityGroup": "observed_layer",
      "description": "The 5th reported layer's cover as a percentage of the dome."
    },
    {
      "key": "cloud_layer_5_cover_code",
      "family": "cloud_cover",
      "quantity": "reported layer cover code",
      "units": "code",
      "level": "reported cloud layer 5",
      "comparabilityGroup": "observed_layer",
      "description": "The coded sky cover (SKC/FEW/SCT/BKN/OVC/VV) of the 5th layer the report lists, in the producer's own order. Never folded into low/middle/high strata: that would be a classification the owner has not approved."
    },
    {
      "key": "cloud_layer_6_base",
      "family": "cloud_geometry",
      "quantity": "reported layer base height",
      "units": "m",
      "level": "reported cloud layer 6",
      "comparabilityGroup": "observed_base",
      "description": "Height above ground of the 6th reported layer's base."
    },
    {
      "key": "cloud_layer_6_cover",
      "family": "cloud_cover",
      "quantity": "reported layer cover",
      "units": "percent",
      "level": "reported cloud layer 6",
      "comparabilityGroup": "observed_layer",
      "description": "The 6th reported layer's cover as a percentage of the dome."
    },
    {
      "key": "cloud_layer_6_cover_code",
      "family": "cloud_cover",
      "quantity": "reported layer cover code",
      "units": "code",
      "level": "reported cloud layer 6",
      "comparabilityGroup": "observed_layer",
      "description": "The coded sky cover (SKC/FEW/SCT/BKN/OVC/VV) of the 6th layer the report lists, in the producer's own order. Never folded into low/middle/high strata: that would be a classification the owner has not approved."
    },
    {
      "key": "cloud_low",
      "family": "cloud_cover",
      "quantity": "low cloud cover",
      "units": "percent",
      "level": "low cloud layer",
      "comparabilityGroup": "provider_stratum",
      "description": "The producer's own low-cloud layer fraction (GFS LCDC). A provider-declared stratum, never a classification made here. No ECCC model publishes cloud by layer on GeoMet at all."
    },
    {
      "key": "cloud_mask_class",
      "family": "cloud_cover",
      "quantity": "clear-sky mask class",
      "units": "code",
      "level": "column",
      "comparabilityGroup": "scene_class",
      "description": "The GOES ABI clear-sky mask's own four-value scene class. A categorical answer, not a fraction, and never averaged into one."
    },
    {
      "key": "cloud_middle",
      "family": "cloud_cover",
      "quantity": "middle cloud cover",
      "units": "percent",
      "level": "middle cloud layer",
      "comparabilityGroup": "provider_stratum",
      "description": "The producer's own middle-cloud layer fraction (GFS MCDC)."
    },
    {
      "key": "cloud_probability",
      "family": "cloud_cover",
      "quantity": "cloud probability",
      "units": "percent",
      "level": "column",
      "comparabilityGroup": "scene_class",
      "description": "The satellite retrieval's own confidence that the scene is cloudy. Not a cover fraction: a certainly-cloudy thin cirrus scene reads 100 here and near zero in opacity-weighted cover."
    },
    {
      "key": "cloud_top_height",
      "family": "cloud_geometry",
      "quantity": "cloud top height",
      "units": "m",
      "level": "cloud top",
      "comparabilityGroup": "satellite_top",
      "description": "Radiatively retrieved height of the highest opaque cloud surface (GOES ABI ACHA). NOAA Provisional maturity."
    },
    {
      "key": "cloud_top_pressure",
      "family": "cloud_geometry",
      "quantity": "cloud top pressure",
      "units": "hPa",
      "level": "cloud top",
      "comparabilityGroup": "satellite_top",
      "description": "Retrieved pressure of the cloud top (GOES ABI CTP)."
    },
    {
      "key": "current_u",
      "family": "marine",
      "quantity": "eastward sea water velocity",
      "units": "m s-1",
      "level": "sea surface",
      "comparabilityGroup": "current",
      "description": "Eastward component of the surface current."
    },
    {
      "key": "current_v",
      "family": "marine",
      "quantity": "northward sea water velocity",
      "units": "m s-1",
      "level": "sea surface",
      "comparabilityGroup": "current",
      "description": "Northward component of the surface current."
    },
    {
      "key": "dew_point_120m",
      "family": "humidity",
      "quantity": "dew point temperature",
      "units": "degC",
      "level": "120 m",
      "comparabilityGroup": "dew_point",
      "description": "Dew point at 120 m."
    },
    {
      "key": "dew_point_2m",
      "family": "humidity",
      "quantity": "dew point temperature",
      "units": "degC",
      "level": "2 m",
      "comparabilityGroup": "dew_point",
      "description": "Screen-level dew point."
    },
    {
      "key": "dew_point_40m",
      "family": "humidity",
      "quantity": "dew point temperature",
      "units": "degC",
      "level": "40 m",
      "comparabilityGroup": "dew_point",
      "description": "Dew point at 40 m (HRDPS _TD_40m; RDPS and GDPS publish DewPoint_2m only)."
    },
    {
      "key": "dew_point_80m",
      "family": "humidity",
      "quantity": "dew point temperature",
      "units": "degC",
      "level": "80 m",
      "comparabilityGroup": "dew_point",
      "description": "Dew point at 80 m."
    },
    {
      "key": "downward_shortwave_accumulated",
      "family": "radiation",
      "quantity": "accumulated downward shortwave radiation",
      "units": "J m-2",
      "level": "surface",
      "comparabilityGroup": "accumulated",
      "description": "Accumulated downward shortwave radiant energy at the surface (HRDPS _N4). Every ECCC global-radiation coverage is an accumulation; no instantaneous W/m2 coverage exists, and the accumulation window is not stated in the WMS title. Differencing steps for a flux would be derived-here."
    },
    {
      "key": "downward_shortwave_flux",
      "family": "radiation",
      "quantity": "downward shortwave radiation flux",
      "units": "W m-2",
      "level": "surface",
      "comparabilityGroup": "flux",
      "description": "Instantaneous downward shortwave flux density. A separate key from the accumulation because converting one to the other is a derivation, not a unit change."
    },
    {
      "key": "dst_index",
      "family": "space_weather",
      "quantity": "disturbance storm time index",
      "units": "nT",
      "level": "planetary",
      "comparabilityGroup": "ring_current_index",
      "description": "The Kyoto WDC quicklook Dst. Reprocessed where it arrives through NOAA SWPC's redistribution rather than from Kyoto directly."
    },
    {
      "key": "fog_closure",
      "family": "visibility",
      "quantity": "fog closure fraction",
      "units": "1",
      "level": "surface",
      "comparabilityGroup": "derived_state",
      "description": "The derived-here fog closure the cloud-and-fog derivation emits, on 0 to 1."
    },
    {
      "key": "fog_state",
      "family": "visibility",
      "quantity": "fog state",
      "units": "code",
      "level": "surface",
      "comparabilityGroup": "derived_state",
      "description": "A fog classification computed here from present-weather codes and visibility by a registered derivation method. Never the producer's own observation."
    },
    {
      "key": "geopotential_height_pressure",
      "family": "pressure",
      "quantity": "geopotential height",
      "units": "gpm",
      "level": "pressure levels",
      "comparabilityGroup": "geopotential",
      "description": "Geopotential height of a pressure surface, level-expanded as geopotential_height_<hPa>hPa. Left in gpm: that is what the message declares and normalize_units has no rule for it."
    },
    {
      "key": "hp30_index",
      "family": "space_weather",
      "quantity": "Hp30 geomagnetic index",
      "units": "1",
      "level": "planetary",
      "comparabilityGroup": "planetary_index",
      "description": "GFZ's half-hourly Hp30 index. Not a resampling of Kp; a separate instrument on a separate cadence."
    },
    {
      "key": "hp60_index",
      "family": "space_weather",
      "quantity": "Hp60 geomagnetic index",
      "units": "1",
      "level": "planetary",
      "comparabilityGroup": "planetary_index",
      "description": "GFZ's hourly Hp60 index."
    },
    {
      "key": "kp_index",
      "family": "space_weather",
      "quantity": "planetary K index",
      "units": "1",
      "level": "planetary",
      "comparabilityGroup": "planetary_index",
      "description": "The 3-hourly planetary K index as retrieved."
    },
    {
      "key": "kp_status",
      "family": "space_weather",
      "quantity": "planetary K index status",
      "units": "flag",
      "level": "planetary",
      "comparabilityGroup": "planetary_index",
      "description": "The producer's own status string for a Kp value (observed, estimated, predicted), carried per value so an outlook is never read as an observation."
    },
    {
      "key": "lightning_observed",
      "family": "lightning",
      "quantity": "lightning detection flag",
      "units": "flag",
      "level": "10-minute gridded interval",
      "comparabilityGroup": "detection",
      "description": "Whether any flash was detected in the interval. An interval with no flashes is a complete answer."
    },
    {
      "key": "lightning_strike",
      "family": "lightning",
      "quantity": "lightning flash density",
      "units": "flash km-2 min-1",
      "level": "10-minute gridded interval",
      "comparabilityGroup": "density",
      "description": "Flash density over the gridded interval. Declared to the manifest only when the interval carried a value, because an all-missing declared field is refused."
    },
    {
      "key": "mean_sea_level_pressure",
      "family": "pressure",
      "quantity": "air pressure at mean sea level",
      "units": "hPa",
      "level": "mean sea level",
      "comparabilityGroup": "mean_sea_level",
      "description": "Pressure reduced to mean sea level by the producer's own reduction."
    },
    {
      "key": "moon_altitude",
      "family": "astronomy_geometry",
      "quantity": "Moon altitude",
      "units": "degree",
      "level": "topocentric",
      "comparabilityGroup": "altitude",
      "description": "Geometric altitude of the Moon's centre above the true horizon, from DE442."
    },
    {
      "key": "moon_azimuth",
      "family": "astronomy_geometry",
      "quantity": "Moon azimuth",
      "units": "degree",
      "level": "topocentric",
      "comparabilityGroup": "azimuth",
      "description": "Bearing of the Moon east of true north, from DE442."
    },
    {
      "key": "moon_illuminated_fraction",
      "family": "astronomy_geometry",
      "quantity": "Moon illuminated fraction",
      "units": "1",
      "level": "topocentric",
      "comparabilityGroup": "phase",
      "description": "Fraction of the Moon's disc illuminated, from DE442."
    },
    {
      "key": "moon_phase_angle",
      "family": "astronomy_geometry",
      "quantity": "Moon phase angle",
      "units": "degree",
      "level": "topocentric",
      "comparabilityGroup": "phase",
      "description": "Sun-Moon-observer angle, from DE442."
    },
    {
      "key": "moon_separation",
      "family": "astronomy_geometry",
      "quantity": "Moon angular separation",
      "units": "degree",
      "level": "topocentric",
      "comparabilityGroup": "separation",
      "description": "Angular separation between the Moon and a named target, from DE442. The target travels with the value."
    },
    {
      "key": "omega_pressure",
      "family": "vertical_motion",
      "quantity": "vertical velocity in pressure coordinates",
      "units": "Pa s-1",
      "level": "pressure levels",
      "comparabilityGroup": "omega",
      "description": "Omega on pressure surfaces, level-expanded as omega_<hPa>hPa. Positive is descent."
    },
    {
      "key": "pm10_surface",
      "family": "air_quality",
      "quantity": "surface PM10 mass concentration",
      "units": "kg m-3",
      "level": "surface",
      "comparabilityGroup": "surface_mass",
      "description": "Surface coarse particulate mass concentration."
    },
    {
      "key": "pm2_5_column",
      "family": "air_quality",
      "quantity": "column PM2.5 mass burden",
      "units": "kg m-2",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "column_mass",
      "description": "Entire-column fine particulate mass burden (RAQDPS EATM_PM2.5). Not comparable with a surface concentration."
    },
    {
      "key": "pm2_5_surface",
      "family": "air_quality",
      "quantity": "surface PM2.5 mass concentration",
      "units": "kg m-3",
      "level": "surface",
      "comparabilityGroup": "surface_mass",
      "description": "Surface fine particulate mass concentration (RAQDPS SFC_PM2.5)."
    },
    {
      "key": "precipitable_water",
      "family": "humidity",
      "quantity": "column water vapour",
      "units": "kg m-2",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "column_vapour",
      "description": "Vertically integrated water vapour. This is the quantity Clear Sky Chart encodes as 'transparency'; it is served here as the moisture field it is and never under the transparency family. No ECCC model publishes it: GFS PWAT and GOES TPW are the only paths into the evidence box."
    },
    {
      "key": "precipitation_accumulation",
      "family": "precipitation",
      "quantity": "precipitation amount",
      "units": "mm",
      "level": "surface",
      "comparabilityGroup": "accumulation",
      "description": "Depth accumulated over the producer's own stated interval, which travels with the value. A one-hour and a three-hour accumulation are not comparable without it."
    },
    {
      "key": "precipitation_rate",
      "family": "precipitation",
      "quantity": "precipitation rate",
      "units": "mm h-1",
      "level": "surface",
      "comparabilityGroup": "rate",
      "description": "Instantaneous precipitation rate."
    },
    {
      "key": "precipitation_type",
      "family": "precipitation",
      "quantity": "precipitation type",
      "units": "code",
      "level": "surface",
      "comparabilityGroup": "type",
      "description": "Categorical precipitation type as the producer codes it."
    },
    {
      "key": "radar_echo",
      "family": "precipitation",
      "quantity": "radar echo detection flag",
      "units": "flag",
      "level": "radar mosaic surface projection",
      "comparabilityGroup": "echo",
      "description": "Whether the radar mosaic detected an echo. Its zero means the mosaic looked and saw nothing, which is why it is a flag and not a rate: publishing that zero as '0 mm/h' would be a measurement nobody made."
    },
    {
      "key": "radiative_surface_temperature",
      "family": "temperature",
      "quantity": "surface radiative temperature",
      "units": "degC",
      "level": "surface",
      "comparabilityGroup": "radiative",
      "description": "Aggregate surface radiative temperature (RDPS/GDPS RadiativeTemp). Kept apart from skin_temperature because their equality is unverified and the air-sea difference that drives Grand Banks advection fog depends on which one is meant."
    },
    {
      "key": "relative_humidity_120m",
      "family": "humidity",
      "quantity": "relative humidity",
      "units": "percent",
      "level": "120 m",
      "comparabilityGroup": "relative",
      "description": "Relative humidity at 120 m."
    },
    {
      "key": "relative_humidity_2m",
      "family": "humidity",
      "quantity": "relative humidity",
      "units": "percent",
      "level": "2 m",
      "comparabilityGroup": "relative",
      "description": "Screen-level relative humidity. Carries the producer's saturation phase as a required attribute; a liquid value and a mixed value are not comparable below 273.16 K."
    },
    {
      "key": "relative_humidity_40m",
      "family": "humidity",
      "quantity": "relative humidity",
      "units": "percent",
      "level": "40 m",
      "comparabilityGroup": "relative",
      "description": "Relative humidity at 40 m (HRDPS _HR_40m; RDPS and GDPS publish specific humidity only at this level)."
    },
    {
      "key": "relative_humidity_80m",
      "family": "humidity",
      "quantity": "relative humidity",
      "units": "percent",
      "level": "80 m",
      "comparabilityGroup": "relative",
      "description": "Relative humidity at 80 m."
    },
    {
      "key": "relative_humidity_pressure",
      "family": "humidity",
      "quantity": "relative humidity",
      "units": "percent",
      "level": "pressure levels",
      "comparabilityGroup": "relative",
      "description": "Relative humidity on pressure surfaces: one field with a level coordinate. GeoMet already stores it that way; the GRIB adapters write it level-expanded as relative_humidity_<hPa>hPa and it resolves back to here."
    },
    {
      "key": "salinity",
      "family": "marine",
      "quantity": "sea water salinity",
      "units": "g kg-1",
      "level": "sea surface",
      "comparabilityGroup": "salinity",
      "description": "Sea-water salinity."
    },
    {
      "key": "sea_ice_fraction",
      "family": "marine",
      "quantity": "sea ice area fraction",
      "units": "1",
      "level": "sea surface",
      "comparabilityGroup": "ice",
      "description": "Fraction of the cell covered by sea ice. HRDPS publishes it analysis-only: its WMS time extent advertised a single instant with PT0H, not a forecast series."
    },
    {
      "key": "sea_surface_temperature",
      "family": "marine",
      "quantity": "sea surface temperature",
      "units": "degC",
      "level": "sea surface",
      "comparabilityGroup": "sea_surface_temperature",
      "description": "Temperature of the sea surface layer. A modelled bulk SST and a satellite skin SST are different measurements of a stratified surface."
    },
    {
      "key": "seeing_arcsec",
      "family": "seeing",
      "quantity": "astronomical seeing",
      "units": "arcsec",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "angular",
      "description": "Angular full width at half maximum of a stellar image, computed here by a registered Cn2 parameterisation over the column. There is no seeing monitor, DIMM or Cn2 profiler anywhere near the evidence box, so this can be compared with the ECCC class index and never validated against a measurement."
    },
    {
      "key": "seeing_class_eccc",
      "family": "seeing",
      "quantity": "seeing class index",
      "units": "1",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "class_index",
      "description": "ECCC RDPS seeing index (RDPS_10km_SeeingIndex). An unlabelled integer class; a live subset decoded to exactly {0, 3, 4, 5}. The class definitions could not be verified from any machine-readable source and CMC is documented as refusing to compute seeing above 80 percent cloud, so 0 may be a masked cell."
    },
    {
      "key": "significant_wave_height",
      "family": "marine",
      "quantity": "significant wave height",
      "units": "m",
      "level": "sea surface",
      "comparabilityGroup": "wave_height",
      "description": "Significant height of the combined wind wave and swell. Not comparable with either partition on its own."
    },
    {
      "key": "skin_temperature",
      "family": "temperature",
      "quantity": "surface skin temperature",
      "units": "degC",
      "level": "surface",
      "comparabilityGroup": "skin",
      "description": "Aggregate land surface skin temperature (HRDPS _SKINT). Not air temperature and not verified equal to RDPS/GDPS aggregate surface radiative temperature."
    },
    {
      "key": "snow_rate",
      "family": "precipitation",
      "quantity": "snowfall rate",
      "units": "cm h-1",
      "level": "surface",
      "comparabilityGroup": "rate",
      "description": "Instantaneous snowfall rate as depth of snow, not water equivalent."
    },
    {
      "key": "solar_wind_density",
      "family": "space_weather",
      "quantity": "solar wind proton density",
      "units": "cm-3",
      "level": "measuring spacecraft at L1",
      "comparabilityGroup": "solar_wind_plasma",
      "description": "Proton number density at L1."
    },
    {
      "key": "solar_wind_speed",
      "family": "space_weather",
      "quantity": "solar wind bulk speed",
      "units": "km s-1",
      "level": "measuring spacecraft at L1",
      "comparabilityGroup": "solar_wind_plasma",
      "description": "Proton bulk speed at L1. An L1 value has not yet reached the magnetosphere; a propagated value is a different instant and is not comparable with it."
    },
    {
      "key": "solar_wind_temperature",
      "family": "space_weather",
      "quantity": "solar wind proton temperature",
      "units": "K",
      "level": "measuring spacecraft at L1",
      "comparabilityGroup": "solar_wind_plasma",
      "description": "Proton temperature at L1."
    },
    {
      "key": "specific_humidity_120m",
      "family": "humidity",
      "quantity": "specific humidity",
      "units": "kg kg-1",
      "level": "120 m",
      "comparabilityGroup": "specific",
      "description": "Specific humidity at 120 m."
    },
    {
      "key": "specific_humidity_2m",
      "family": "humidity",
      "quantity": "specific humidity",
      "units": "kg kg-1",
      "level": "2 m",
      "comparabilityGroup": "specific",
      "description": "Mass of water vapour per mass of moist air at screen level. Carries no phase ambiguity, which is why it is what the phase attribute on relative humidity is measured against."
    },
    {
      "key": "specific_humidity_40m",
      "family": "humidity",
      "quantity": "specific humidity",
      "units": "kg kg-1",
      "level": "40 m",
      "comparabilityGroup": "specific",
      "description": "Specific humidity at 40 m. The only humidity RDPS and GDPS publish at this level."
    },
    {
      "key": "specific_humidity_80m",
      "family": "humidity",
      "quantity": "specific humidity",
      "units": "kg kg-1",
      "level": "80 m",
      "comparabilityGroup": "specific",
      "description": "Specific humidity at 80 m."
    },
    {
      "key": "storm_surge",
      "family": "marine",
      "quantity": "storm surge water level",
      "units": "m",
      "level": "sea surface",
      "comparabilityGroup": "surge",
      "description": "Water level departure attributable to meteorological forcing."
    },
    {
      "key": "sun_altitude",
      "family": "astronomy_geometry",
      "quantity": "Sun altitude",
      "units": "degree",
      "level": "topocentric",
      "comparabilityGroup": "altitude",
      "description": "Geometric altitude of the Sun's centre above the true horizon, computed here from the pinned JPL DE442 ephemeris by the registered geometry method."
    },
    {
      "key": "sun_azimuth",
      "family": "astronomy_geometry",
      "quantity": "Sun azimuth",
      "units": "degree",
      "level": "topocentric",
      "comparabilityGroup": "azimuth",
      "description": "Bearing of the Sun east of true north, from DE442."
    },
    {
      "key": "surface_height",
      "family": "terrain",
      "quantity": "surface altitude",
      "units": "m",
      "level": "surface (model orography)",
      "comparabilityGroup": "orography",
      "description": "The model's own orography (HRDPS HGT_Sfc, paramId 228002, metres). Not a geopotential height; it is the AGL datum the WEonG low-cloud diagnosis is written against."
    },
    {
      "key": "surface_pressure",
      "family": "pressure",
      "quantity": "surface air pressure",
      "units": "Pa",
      "level": "surface",
      "comparabilityGroup": "surface",
      "description": "Pressure at the producer's own surface height. Left in Pa: the hPa conversion in ingest.grib.normalize_units keys on the decoded variable name and this one decodes as 'sp'."
    },
    {
      "key": "swell_height",
      "family": "marine",
      "quantity": "swell height",
      "units": "m",
      "level": "sea surface",
      "comparabilityGroup": "wave_partition",
      "description": "Significant height of the swell partition."
    },
    {
      "key": "temperature_120m",
      "family": "temperature",
      "quantity": "air temperature",
      "units": "degC",
      "level": "120 m",
      "comparabilityGroup": "air",
      "description": "Air temperature at 120 m above ground."
    },
    {
      "key": "temperature_2m",
      "family": "temperature",
      "quantity": "air temperature",
      "units": "degC",
      "level": "2 m",
      "comparabilityGroup": "air",
      "description": "Screen-level air temperature."
    },
    {
      "key": "temperature_40m",
      "family": "temperature",
      "quantity": "air temperature",
      "units": "degC",
      "level": "40 m",
      "comparabilityGroup": "air",
      "description": "Air temperature at 40 m above ground. HRDPS publishes it as _TT_40m; RDPS and GDPS as AirTemp_40m."
    },
    {
      "key": "temperature_80m",
      "family": "temperature",
      "quantity": "air temperature",
      "units": "degC",
      "level": "80 m",
      "comparabilityGroup": "air",
      "description": "Air temperature at 80 m above ground."
    },
    {
      "key": "temperature_pressure",
      "family": "temperature",
      "quantity": "air temperature",
      "units": "degC",
      "level": "pressure levels",
      "comparabilityGroup": "air",
      "description": "Air temperature on pressure surfaces. One field with a level coordinate; the GRIB adapters write it level-expanded as temperature_<hPa>hPa and it resolves back to here."
    },
    {
      "key": "total_cloud_geometric",
      "family": "cloud_cover",
      "quantity": "geometric total cloud cover",
      "units": "percent",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "geometric_column",
      "description": "Whole-column cloud fraction from a maximum-random overlap of layer fractions, as GFS (TCDC entire atmosphere), ECMWF (tcc) and ICON (clct) publish it. Thin cirrus counts in full. Not comparable with an opacity-weighted cover."
    },
    {
      "key": "total_cloud_mean_6h",
      "family": "cloud_cover",
      "quantity": "six-hour mean total cloud cover",
      "units": "percent",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "time_mean_column",
      "description": "Column cloud cover averaged over the producer's forecast block, as GEFS publishes it: 0-3 hour ave at f003 and 6 h thereafter. GEFS publishes no instantaneous column cloud at all, so this key never stands in for one and is never served under an instantaneous key."
    },
    {
      "key": "total_cloud_okta",
      "family": "cloud_cover",
      "quantity": "observed sky cover",
      "units": "percent",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "observed_dome",
      "description": "One observer's fraction of the celestial dome covered, reported in eighths and converted to percent. A point observation over one station, not a grid cell, and not comparable with any modelled column cover."
    },
    {
      "key": "total_cloud_opacity",
      "family": "cloud_cover",
      "quantity": "opacity-weighted total cloud cover",
      "units": "percent",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "opacity_weighted_column",
      "description": "Whole-column cloud cover weighted by how much light each layer stops, as ECCC GEM publishes it (HRDPS.CONTINENTAL_NT, RDPS_10km_TotalCloudCover, GDPS_15km_TotalCloudCover, REPS ETA_NT). Thin cirrus reads near zero. Not comparable with a geometric fraction."
    },
    {
      "key": "total_cloud_weong",
      "family": "cloud_cover",
      "quantity": "opacity-weighted total cloud cover, WEonG low-cloud repair",
      "units": "percent",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "derived_repair",
      "description": "ECCC's own WEonG technical note states HRDPS published NT under-reports low cloud and repairs it from the RH profile. This key carries that repair, computed here, and is always served beside total_cloud_opacity rather than replacing it."
    },
    {
      "key": "transparency_class_eccc",
      "family": "transparency",
      "quantity": "sky transparency class index",
      "units": "1",
      "level": "entire atmosphere (column)",
      "comparabilityGroup": "class_index",
      "description": "ECCC RDPS sky transparency index (RDPS_10km_SkyTransparencyIndex). An unlabelled integer class; a live subset decoded to exactly {0, 2, 3, 4} across all 8113 cells and the WMS leaf title carries no unit bracket. Whether 0 is a class or a not-computed sentinel is unresolved, and CMC is documented as refusing to compute transparency above 30 percent cloud, so 0 may be a masked cell rather than 'worst'."
    },
    {
      "key": "transparency_extinction",
      "family": "transparency",
      "quantity": "atmospheric extinction",
      "units": "mag airmass-1",
      "level": "zenith",
      "comparabilityGroup": "extinction",
      "description": "Atmospheric extinction in magnitudes per air mass. A third encoding, comparable with neither of the others."
    },
    {
      "key": "transparency_limiting_magnitude",
      "family": "transparency",
      "quantity": "naked-eye limiting magnitude",
      "units": "mag",
      "level": "zenith",
      "comparabilityGroup": "limiting_magnitude",
      "description": "Faintest stellar magnitude visible to the unaided eye at the zenith. A different encoding of transparency from the class index and not convertible into it."
    },
    {
      "key": "twilight_state",
      "family": "astronomy_geometry",
      "quantity": "twilight state",
      "units": "code",
      "level": "topocentric",
      "comparabilityGroup": "twilight",
      "description": "Day, civil, nautical, astronomical or night, from the Sun's DE442 altitude at the standard boundaries."
    },
    {
      "key": "visibility",
      "family": "visibility",
      "quantity": "horizontal visibility",
      "units": "m",
      "level": "surface",
      "comparabilityGroup": "horizontal",
      "description": "Prevailing horizontal visibility."
    },
    {
      "key": "wave_direction",
      "family": "marine",
      "quantity": "wave direction",
      "units": "degree",
      "level": "sea surface",
      "comparabilityGroup": "wave_direction",
      "description": "Mean direction of the sea state."
    },
    {
      "key": "wave_period",
      "family": "marine",
      "quantity": "wave period",
      "units": "s",
      "level": "sea surface",
      "comparabilityGroup": "wave_period",
      "description": "Mean or peak period of the sea state, as the producer defines it."
    },
    {
      "key": "weather_fog_code",
      "family": "visibility",
      "quantity": "present-weather fog flag",
      "units": "flag",
      "level": "surface",
      "comparabilityGroup": "present_weather_flag",
      "description": "Fog read out of the METAR/TAF present-weather group (WMO No. 306 FM 15 table 4678). Retrieved: it is what the report said, not a judgement made here. Mist (BR) is a different phenomenon and is not this flag."
    },
    {
      "key": "wind_direction_10m",
      "family": "wind",
      "quantity": "wind direction",
      "units": "degree",
      "level": "10 m",
      "comparabilityGroup": "direction",
      "description": "Bearing the 10 m wind comes from, meteorological convention. Stays null for a speed-only product; nothing derives a direction from a speed."
    },
    {
      "key": "wind_direction_120m",
      "family": "wind",
      "quantity": "wind direction",
      "units": "degree",
      "level": "120 m",
      "comparabilityGroup": "direction",
      "description": "Wind direction at 120 m."
    },
    {
      "key": "wind_direction_40m",
      "family": "wind",
      "quantity": "wind direction",
      "units": "degree",
      "level": "40 m",
      "comparabilityGroup": "direction",
      "description": "Wind direction at 40 m."
    },
    {
      "key": "wind_direction_80m",
      "family": "wind",
      "quantity": "wind direction",
      "units": "degree",
      "level": "80 m",
      "comparabilityGroup": "direction",
      "description": "Wind direction at 80 m."
    },
    {
      "key": "wind_direction_pressure",
      "family": "wind",
      "quantity": "wind direction",
      "units": "degree",
      "level": "pressure levels",
      "comparabilityGroup": "direction",
      "description": "Wind direction on pressure surfaces, level-expanded as wind_direction_<hPa>hPa."
    },
    {
      "key": "wind_gust_10m",
      "family": "wind",
      "quantity": "wind gust speed",
      "units": "m s-1",
      "level": "10 m",
      "comparabilityGroup": "gust",
      "description": "Peak gust over the producer's own reporting interval, which travels with the value."
    },
    {
      "key": "wind_speed_10m",
      "family": "wind",
      "quantity": "wind speed",
      "units": "m s-1",
      "level": "10 m",
      "comparabilityGroup": "speed",
      "description": "Scalar 10 m wind speed as the producer publishes it, or derived here from components; the class says which."
    },
    {
      "key": "wind_speed_120m",
      "family": "wind",
      "quantity": "wind speed",
      "units": "m s-1",
      "level": "120 m",
      "comparabilityGroup": "speed",
      "description": "Wind speed at 120 m."
    },
    {
      "key": "wind_speed_40m",
      "family": "wind",
      "quantity": "wind speed",
      "units": "m s-1",
      "level": "40 m",
      "comparabilityGroup": "speed",
      "description": "Wind speed at 40 m. GeoMet publishes speed and direction at 40/80/120 m and no components anywhere."
    },
    {
      "key": "wind_speed_80m",
      "family": "wind",
      "quantity": "wind speed",
      "units": "m s-1",
      "level": "80 m",
      "comparabilityGroup": "speed",
      "description": "Wind speed at 80 m."
    },
    {
      "key": "wind_speed_pressure",
      "family": "wind",
      "quantity": "wind speed",
      "units": "m s-1",
      "level": "pressure levels",
      "comparabilityGroup": "speed",
      "description": "Wind speed on pressure surfaces (GeoMet WSPD/WindSpeed), level-expanded as wind_speed_<hPa>hPa."
    },
    {
      "key": "wind_u_10m",
      "family": "wind",
      "quantity": "eastward wind component",
      "units": "m s-1",
      "level": "10 m",
      "comparabilityGroup": "component",
      "description": "Eastward component of the 10 m wind."
    },
    {
      "key": "wind_u_pressure",
      "family": "wind",
      "quantity": "eastward wind component",
      "units": "m s-1",
      "level": "pressure levels",
      "comparabilityGroup": "component",
      "description": "Eastward wind on pressure surfaces: one field with a level coordinate. Written level-expanded as wind_u_<hPa>hPa by the GRIB adapters."
    },
    {
      "key": "wind_v_10m",
      "family": "wind",
      "quantity": "northward wind component",
      "units": "m s-1",
      "level": "10 m",
      "comparabilityGroup": "component",
      "description": "Northward component of the 10 m wind."
    },
    {
      "key": "wind_v_pressure",
      "family": "wind",
      "quantity": "northward wind component",
      "units": "m s-1",
      "level": "pressure levels",
      "comparabilityGroup": "component",
      "description": "Northward wind on pressure surfaces, level-expanded as wind_v_<hPa>hPa."
    },
    {
      "key": "wind_wave_height",
      "family": "marine",
      "quantity": "wind wave height",
      "units": "m",
      "level": "sea surface",
      "comparabilityGroup": "wave_partition",
      "description": "Significant height of the wind-sea partition."
    },
    {
      "key": "xray_flux_long",
      "family": "space_weather",
      "quantity": "solar X-ray flux, 0.1-0.8 nm",
      "units": "W m-2",
      "level": "geosynchronous orbit",
      "comparabilityGroup": "xray_flux",
      "description": "GOES XRS long-channel flux. Flare context, typically two to three days upstream of any aurora."
    },
    {
      "key": "xray_flux_short",
      "family": "space_weather",
      "quantity": "solar X-ray flux, 0.05-0.4 nm",
      "units": "W m-2",
      "level": "geosynchronous orbit",
      "comparabilityGroup": "xray_flux",
      "description": "GOES XRS short-channel flux."
    }
  ]
}

export const CATALOGUE_FAMILIES: Record<string, CatalogueFamilyCopy> = Object.fromEntries(
  FIELD_CATALOGUE_COPY.families.map((family) => [family.name, family]),
)

export const CATALOGUE_FIELDS: Record<string, CatalogueFieldCopy> = Object.fromEntries(
  FIELD_CATALOGUE_COPY.fields.map((field) => [field.key, field]),
)
