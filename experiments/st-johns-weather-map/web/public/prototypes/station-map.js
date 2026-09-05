// Reference geography styling copied from the settled Map prototype.
const REF_ANCHOR="reference-water-casing";
export function baseStyle(theme) {
  const dark = theme !== 'light';
  const c = dark ? { land: '#527267', ocean: '#071D2A', park: '#476A5C', urban: '#5D746D', casing: '#07151C', core: '#F7FBFA', road: '#F2B85B', label: '#F7FBFA', labelHalo: '#07151C', boundary: '#D6E5E3', waterLabel: '#A9E1EA' }
                 : { land: '#F2E8D5', ocean: '#4B899A', park: '#D7E4CE', urban: '#E5D8C5', casing: '#183039', core: '#FFFFFF', road: '#8A5200', label: '#15282F', labelHalo: '#FBFAF5', boundary: '#38565E', waterLabel: '#123E4A' };
  if (theme === 'night') Object.assign(c, { land: '#1a0000', ocean: '#000000', park: '#200000', urban: '#240000', casing: '#000', core: '#7a1a14', road: '#8a1f1a', label: '#ff3b30', labelHalo: '#000', boundary: '#6a1510', waterLabel: '#b3261e' });
  const S = 'openfreemap';
  return { version: 8, glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: { [S]: { type: 'vector', url: 'https://tiles.openfreemap.org/planet', attribution: '© OpenMapTiles © OpenStreetMap contributors' } },
    layers: [
      { id: 'base-land', type: 'background', paint: { 'background-color': c.land } },
      { id: 'base-landcover', type: 'fill', source: S, 'source-layer': 'landcover', minzoom: 5, paint: { 'fill-color': c.park, 'fill-opacity': 0.3 } },
      { id: 'base-park', type: 'fill', source: S, 'source-layer': 'park', minzoom: 6, paint: { 'fill-color': c.park, 'fill-opacity': 0.48 } },
      { id: 'base-urban', type: 'fill', source: S, 'source-layer': 'landuse', minzoom: 7, filter: ['==', ['get', 'class'], 'residential'], paint: { 'fill-color': c.urban, 'fill-opacity': 0.42 } },
      { id: 'base-water', type: 'fill', source: S, 'source-layer': 'water', paint: { 'fill-color': c.ocean } },
      { id: REF_ANCHOR, type: 'line', source: S, 'source-layer': 'water', paint: { 'line-color': c.casing, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 1.8, 10, 4], 'line-opacity': 0.9 } },
      { id: 'reference-water-core', type: 'line', source: S, 'source-layer': 'water', paint: { 'line-color': c.core, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.75, 10, 1.6], 'line-opacity': 0.9 } },
      { id: 'reference-road-casing', type: 'line', source: S, 'source-layer': 'transportation', minzoom: 5, filter: ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary', 'tertiary']]], paint: { 'line-color': c.casing, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.2, 13, 5.5], 'line-opacity': 0.88 } },
      { id: 'reference-road-core', type: 'line', source: S, 'source-layer': 'transportation', minzoom: 5, filter: ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary', 'tertiary']]], paint: { 'line-color': c.road, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.45, 13, 2.2], 'line-opacity': 0.92 } },
      { id: 'reference-boundary', type: 'line', source: S, 'source-layer': 'boundary', minzoom: 3, filter: ['<=', ['get', 'admin_level'], 4], paint: { 'line-color': c.boundary, 'line-width': 1, 'line-dasharray': [4, 3], 'line-opacity': 0.72 } },
      { id: 'reference-water-label', type: 'symbol', source: S, 'source-layer': 'water_name', minzoom: 5, layout: { 'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']], 'text-font': ['Noto Sans Italic'], 'text-size': ['interpolate', ['linear'], ['zoom'], 5, 10, 11, 14], 'symbol-placement': 'point' }, paint: { 'text-color': c.waterLabel, 'text-halo-color': c.labelHalo, 'text-halo-width': 1.7 } },
      { id: 'reference-place-label', type: 'symbol', source: S, 'source-layer': 'place', minzoom: 4, layout: { 'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 4, 11, 11, 15], 'text-padding': 4 }, paint: { 'text-color': c.label, 'text-halo-color': c.labelHalo, 'text-halo-width': 2 } },
    ] };
}
