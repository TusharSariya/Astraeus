/** Owner-selected Newfoundland UI scope. Keep the API/registry audit intact.
 * Only documented geographic exclusions belong here, never access or read failures.
 */
const excludedFromNewfoundland = new Set([
  // CAMS Europe pollen and ammonia do not cover Newfoundland.
  // https://open-meteo.com/en/docs/air-quality-api (checked 2026-09-08)
  'openmeteo-pollen-ammonia',
])

export const isNewfoundlandSource = (sourceId: string): boolean => !excludedFromNewfoundland.has(sourceId)

/** Supersession is declared by the registry, never inferred from a date or name. */
export const isVisibleSource = (sourceId: string, state: string): boolean =>
  isNewfoundlandSource(sourceId) && state !== 'superseded'
