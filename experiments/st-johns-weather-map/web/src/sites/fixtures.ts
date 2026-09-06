import type { HorizonDependentField, Site, SiteRegistry } from './types'

/** Three fixture sites mirroring the shape of `registry/sites/*.yaml`
 *  (Signal Hill, Cape Spear, Quidi Vidi), trimmed to a handful of bearings so
 *  tests stay readable. Real records carry 36 values at 10-degree steps. */
export function fixtureSite(overrides: Partial<Site> = {}): Site {
  return {
    id: 'signal-hill',
    name: 'Signal Hill (Cabot Tower)',
    latitude: 47.5704,
    longitude: -52.6816,
    elevation_m: 140.0,
    datum: 'CGVD2013',
    horizon: {
      site_id: 'signal-hill',
      bearing_resolution_deg: 90,
      elevation_deg: [0.5, -0.5, 4.0, 1.5],
      terrain_check_status: 'not_run',
      terrain_check_note: 'No digital elevation model is available in the repository; the terrain check was not run and the terrain horizon is not assumed to agree.',
    },
    registered_on: '2026-09-03',
    registered_by: 'Tushar Sariya',
    ...overrides,
  }
}

export function fixtureRegistry(overrides: Partial<SiteRegistry> = {}): SiteRegistry {
  return {
    sites: [
      fixtureSite(),
      fixtureSite({
        id: 'cape-spear',
        name: 'Cape Spear (lighthouse headland)',
        latitude: 47.5233,
        longitude: -52.6224,
        elevation_m: 75.0,
        horizon: {
          site_id: 'cape-spear',
          bearing_resolution_deg: 90,
          elevation_deg: [1.0, -0.5, 1.5, 3.0],
          terrain_check_status: 'not_run',
          terrain_check_note: 'No digital elevation model is available in the repository; the terrain check was not run and the terrain horizon is not assumed to agree.',
        },
      }),
      fixtureSite({
        id: 'quidi-vidi',
        name: 'Quidi Vidi Lake (boathouses)',
        latitude: 47.5806,
        longitude: -52.6867,
        elevation_m: 5.0,
        horizon: {
          site_id: 'quidi-vidi',
          bearing_resolution_deg: 90,
          elevation_deg: [8.0, 0.5, 11.0, 4.0],
          terrain_check_status: 'passed',
          terrain_check_note: '',
        },
      }),
    ],
    notice: null,
    ...overrides,
  }
}

export function fixtureHorizonField(overrides: Partial<HorizonDependentField> = {}): HorizonDependentField {
  return {
    field: 'sector_statistic',
    value: null,
    quality: { status: 'unavailable', flags: ['no_registered_horizon'] },
    absence_state: 'null',
    ...overrides,
  }
}
