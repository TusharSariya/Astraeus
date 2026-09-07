import { expect, it } from 'vitest'
import { isSourceCapability, isSourceConfiguration, isSourceVariant } from './sourceContract'

it('rejects ambiguous member/statistic identities rather than offering a different variant', () => {
  expect(isSourceVariant({ kind: 'member', member: '01' })).toBe(true)
  expect(isSourceVariant({ kind: 'member' })).toBe(false)
  expect(isSourceVariant({ kind: 'deterministic', member: '01' })).toBe(false)
  expect(isSourceVariant({ kind: 'provider_statistic', statistic: 'percentile', quantile: 0 })).toBe(true)
  expect(isSourceVariant({ kind: 'provider_statistic', statistic: 'percentile', quantile: 2 })).toBe(false)
  expect(isSourceVariant({ kind: 'provider_statistic', statistic: 'probability', threshold: 0 })).toBe(false)
})
it('rejects malformed capabilities and unknown configuration states', () => {
  expect(isSourceCapability({ source_id: 'other', native_series: true }, 'selected')).toBe(false)
  expect(isSourceConfiguration({ state: 'available', reason: 'Not a configuration disposition', required_environment: [] })).toBe(false)
  expect(isSourceConfiguration({ state: 'ready', reason: 'Assessed', required_environment: 'PRIVATE_VALUE' })).toBe(false)
  expect(isSourceConfiguration({ state: 'ready', reason: 'Assessed', required_environment: [], checked_at: 'yesterday' })).toBe(false)
})

it('keeps zero thresholds and quantiles in named statistics', () => {
  expect(isSourceVariant({ kind: 'provider_statistic', statistic: 'probability', threshold: 0, comparison: 'greater_than' })).toBe(true)
  expect(isSourceVariant({ kind: 'derived_statistic', statistic: 'percentile', quantile: 0 })).toBe(true)
  expect(isSourceVariant({ kind: 'deterministic', threshold: 0, comparison: 'greater_than' })).toBe(false)
})
