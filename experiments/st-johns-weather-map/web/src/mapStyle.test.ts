import { describe, expect, it } from 'vitest'
import { createWeatherMapStyle, WEATHER_REFERENCE_ANCHOR_ID } from './mapStyle'

describe('owned weather map style', () => {
  it('keeps a stable insertion boundary between base geography and reference detail', () => {
    const style = createWeatherMapStyle('dark')
    expect(style.sources.openfreemap).toMatchObject({ type: 'vector', url: 'https://tiles.openfreemap.org/planet' })
    const ids = style.layers.map((layer) => layer.id)
    const anchor = ids.indexOf(WEATHER_REFERENCE_ANCHOR_ID)
    expect(anchor).toBeGreaterThan(ids.indexOf('base-water'))
    expect(ids.indexOf('reference-road-core')).toBeGreaterThan(anchor)
    expect(ids.indexOf('reference-place-label')).toBeGreaterThan(anchor)
  })

  it('changes cartographic tokens without changing the layer or source contract', () => {
    const dark = createWeatherMapStyle('dark')
    const light = createWeatherMapStyle('light')
    expect(light.layers.map((layer) => layer.id)).toEqual(dark.layers.map((layer) => layer.id))
    expect(light.sources).toEqual(dark.sources)
    expect(light.layers[0]).not.toEqual(dark.layers[0])
  })
})
