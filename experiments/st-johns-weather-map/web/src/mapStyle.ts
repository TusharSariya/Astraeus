import type { Map as MapLibreMap, StyleSpecification } from 'maplibre-gl'

export type Theme = 'light' | 'dark'

export const REFERENCE_SOURCE_ID = 'openfreemap'
export const WEATHER_REFERENCE_ANCHOR_ID = 'reference-water-casing'

const themes = {
  dark: {
    land: '#527267', ocean: '#071D2A', park: '#476A5C', urban: '#5D746D',
    casing: '#07151C', core: '#F7FBFA', road: '#F2B85B', label: '#F7FBFA',
    labelHalo: '#07151C', boundary: '#D6E5E3', waterLabel: '#A9E1EA',
  },
  light: {
    land: '#F2E8D5', ocean: '#4B899A', park: '#D7E4CE', urban: '#E5D8C5',
    casing: '#183039', core: '#FFFFFF', road: '#8A5200', label: '#15282F',
    labelHalo: '#FBFAF5', boundary: '#38565E', waterLabel: '#123E4A',
  },
} as const

const reference = (theme: Theme) => themes[theme]

/** The source is hosted, but the cartography is ours: no remote style JSON can
 * silently move weather below labels or replace the deliberately sparse visual
 * hierarchy. */
export function createWeatherMapStyle(theme: Theme): StyleSpecification {
  const c = reference(theme)
  return {
    version: 8,
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sprite: 'https://tiles.openfreemap.org/sprites/ofm_f384/ofm',
    sources: {
      [REFERENCE_SOURCE_ID]: {
        type: 'vector',
        url: 'https://tiles.openfreemap.org/planet',
        attribution: '© OpenMapTiles © OpenStreetMap contributors',
      },
    },
    layers: [
      { id: 'base-land', type: 'background', paint: { 'background-color': c.land } },
      { id: 'base-landcover', type: 'fill', source: REFERENCE_SOURCE_ID, 'source-layer': 'landcover', minzoom: 5, paint: { 'fill-color': c.park, 'fill-opacity': 0.3 } },
      { id: 'base-park', type: 'fill', source: REFERENCE_SOURCE_ID, 'source-layer': 'park', minzoom: 6, paint: { 'fill-color': c.park, 'fill-opacity': 0.48 } },
      { id: 'base-urban', type: 'fill', source: REFERENCE_SOURCE_ID, 'source-layer': 'landuse', minzoom: 7, filter: ['==', ['get', 'class'], 'residential'], paint: { 'fill-color': c.urban, 'fill-opacity': 0.42 } },
      { id: 'base-water', type: 'fill', source: REFERENCE_SOURCE_ID, 'source-layer': 'water', paint: { 'fill-color': c.ocean } },

      // Everything below this first reference layer may be covered by weather.
      { id: WEATHER_REFERENCE_ANCHOR_ID, type: 'line', source: REFERENCE_SOURCE_ID, 'source-layer': 'water', paint: { 'line-color': c.casing, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 1.8, 10, 4], 'line-opacity': 0.9 } },
      { id: 'reference-water-core', type: 'line', source: REFERENCE_SOURCE_ID, 'source-layer': 'water', paint: { 'line-color': c.core, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.75, 10, 1.6], 'line-opacity': 0.9 } },
      { id: 'reference-waterway-casing', type: 'line', source: REFERENCE_SOURCE_ID, 'source-layer': 'waterway', minzoom: 8, paint: { 'line-color': c.casing, 'line-width': 2.5, 'line-opacity': 0.78 } },
      { id: 'reference-waterway-core', type: 'line', source: REFERENCE_SOURCE_ID, 'source-layer': 'waterway', minzoom: 8, paint: { 'line-color': c.core, 'line-width': 0.8, 'line-opacity': 0.86 } },
      { id: 'reference-road-casing', type: 'line', source: REFERENCE_SOURCE_ID, 'source-layer': 'transportation', minzoom: 5, filter: ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary', 'tertiary']]], paint: { 'line-color': c.casing, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.2, 13, 5.5], 'line-opacity': 0.88 } },
      { id: 'reference-road-core', type: 'line', source: REFERENCE_SOURCE_ID, 'source-layer': 'transportation', minzoom: 5, filter: ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary', 'tertiary']]], paint: { 'line-color': c.road, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.45, 13, 2.2], 'line-opacity': 0.92 } },
      { id: 'reference-boundary', type: 'line', source: REFERENCE_SOURCE_ID, 'source-layer': 'boundary', minzoom: 3, filter: ['<=', ['get', 'admin_level'], 4], paint: { 'line-color': c.boundary, 'line-width': 1, 'line-dasharray': [4, 3], 'line-opacity': 0.72 } },
      { id: 'reference-water-label', type: 'symbol', source: REFERENCE_SOURCE_ID, 'source-layer': 'water_name', minzoom: 5, layout: { 'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']], 'text-font': ['Noto Sans Italic'], 'text-size': ['interpolate', ['linear'], ['zoom'], 5, 10, 11, 14], 'symbol-placement': 'point' }, paint: { 'text-color': c.waterLabel, 'text-halo-color': c.labelHalo, 'text-halo-width': 1.7 } },
      { id: 'reference-road-label', type: 'symbol', source: REFERENCE_SOURCE_ID, 'source-layer': 'transportation_name', minzoom: 10, layout: { 'text-field': ['coalesce', ['get', 'ref'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': 10, 'symbol-placement': 'line' }, paint: { 'text-color': c.label, 'text-halo-color': c.labelHalo, 'text-halo-width': 1.8 } },
      { id: 'reference-place-label', type: 'symbol', source: REFERENCE_SOURCE_ID, 'source-layer': 'place', minzoom: 4, layout: { 'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 4, 11, 11, 15], 'text-padding': 4 }, paint: { 'text-color': c.label, 'text-halo-color': c.labelHalo, 'text-halo-width': 2 } },
    ],
  }
}

const themedPaints: Record<string, string> = {
  'base-land.background-color': 'land', 'base-landcover.fill-color': 'park',
  'base-park.fill-color': 'park', 'base-urban.fill-color': 'urban',
  'base-water.fill-color': 'ocean', 'reference-water-casing.line-color': 'casing',
  'reference-water-core.line-color': 'core', 'reference-waterway-casing.line-color': 'casing',
  'reference-waterway-core.line-color': 'core', 'reference-road-casing.line-color': 'casing',
  'reference-road-core.line-color': 'road', 'reference-boundary.line-color': 'boundary',
  'reference-water-label.text-color': 'waterLabel', 'reference-water-label.text-halo-color': 'labelHalo',
  'reference-road-label.text-color': 'label', 'reference-road-label.text-halo-color': 'labelHalo',
  'reference-place-label.text-color': 'label', 'reference-place-label.text-halo-color': 'labelHalo',
}

export function applyWeatherMapTheme(map: MapLibreMap, theme: Theme) {
  const c = reference(theme)
  for (const [qualified, token] of Object.entries(themedPaints)) {
    const separator = qualified.indexOf('.')
    const layer = qualified.slice(0, separator)
    const property = qualified.slice(separator + 1)
    if (map.getLayer(layer)) map.setPaintProperty(layer, property, c[token as keyof typeof c])
  }
}
