import { expect, it } from 'vitest'
import { observationReceipt } from './observationReceipt'
import { normalizePoint } from './api'
const receipt = { provider_url: 'https://geo.weather.gc.ca/geomet', effective_url: 'https://geo.weather.gc.ca/geomet',
  cached_at: '2026-09-07T12:00:00Z', expires_at: '2026-09-07T12:05:00Z', transport_completed_at: '2026-09-07T12:00:00Z',
  body_bytes: 100, body_sha256: 'a'.repeat(64), request_headers: { accept: 'application/json' }, response_headers: { 'content-type': 'application/json' } }
it('strips arbitrary receipt/header/request keys from valid AQHI and SWOB metadata', () => {
  expect(observationReceipt('eccc-aqhi', { ...receipt, raw_exception: 'private', request_headers: { ...receipt.request_headers, authorization: 'private' } })).toEqual(receipt)
  const { provider_url, ...common } = receipt
  const request = { source_id: 'eccc-swob', selected_time: receipt.cached_at, latitude: 47.5, longitude: -52.7, provider_url }
  expect(observationReceipt('eccc-swob', { ...common, raw_exception: 'private', request: { ...request, raw_exception: 'private' } })).toEqual({ ...common, request })
})
it('withholds malformed nested receipts while retaining the safe independent failure', () => {
  for (const expired_acquisition of [null, false, { raw_exception: 'private' }, { ...receipt, body_bytes: -1 }, { ...receipt, expires_at: 'invalid' },
    { ...receipt, request_headers: { accept: {} } }, { ...receipt, body_sha256: 'wrong' }, { ...receipt, effective_url: 'https://user:password@example.com' }]) {
    const snapshot = normalizePoint({ valid_time: receipt.cached_at, fields: [], selection: { mode: 'fallback', badge: 'HRDPS', selected_source_id: 'eccc-hrdps' },
      observation_unavailable: [{ source_id: 'eccc-aqhi', reason: 'query_failed', error_type: 'HTTPStatusError', values_withheld: true, expired_acquisition }] })
    expect(snapshot.selectedSourceId).toBe('eccc-hrdps')
    expect(snapshot.observationUnavailable).toEqual([{ source_id: 'eccc-aqhi', reason: 'query_failed', error_type: 'HTTPStatusError', values_withheld: true, expired_acquisition: null }])
  }
  expect(observationReceipt('eccc-swob', { ...receipt, request: { source_id: 'eccc-swob', latitude: 91, longitude: 0, selected_time: receipt.cached_at, provider_url: receipt.provider_url } })).toBeNull()
})
