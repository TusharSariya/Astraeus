import type { CameraDerivedField, CameraFrame, CameraMethod, CameraRecord } from './types'

/** A `partnership-only` camera, shaped like `registry/cameras/ccg-fort-amherst.yaml`:
 *  a courtesy notice, an outstanding permission request, and an incomplete
 *  registration (no operator has published position, bearing or field of
 *  view for this camera, per `docs/research/wayfinder/camera-inventory.md`). */
export function fixturePartnershipCamera(overrides: Partial<CameraRecord> = {}): CameraRecord {
  return {
    id: 'ccg-fort-amherst',
    name: 'Fort Amherst',
    operator: 'Canadian Coast Guard',
    source_id: 'ccg-harbour-cameras',
    status: 'partnership-only',
    terms: {
      text: 'these cameras are intented for operational use for the CCG. The images are offered to the public as a courtesy and are for information only.',
      url: 'https://e-navigation.canada.ca/topics/cameras/camera-en?camfile=FortAmherst',
      permission: {
        requested_on: '2026-09-02',
        requested_from: 'Canadian Coast Guard',
        granted_on: null,
      },
    },
    registration: {
      status: 'incomplete',
      missing: ['orientation.bearing_deg', 'orientation.hfov_deg', 'landmarks'],
    },
    ...overrides,
  }
}

/** A camera admitted for retrieval but with every method still gated on the
 *  30-day validation: frames and health flags are served, no derived claim
 *  is. */
export function fixtureAwaitingValidationCamera(overrides: Partial<CameraRecord> = {}): CameraRecord {
  return {
    id: 'ntv-st-johns-sky',
    name: 'St. John\'s Sky',
    operator: 'NTV',
    source_id: 'ntv-cameras',
    status: 'awaiting_validation',
    terms: {
      text: 'Images are provided for informational purposes.',
      url: 'https://ntv.ca/weather/cameras',
      permission: {
        requested_on: '2026-09-01',
        requested_from: 'NTV',
        granted_on: '2026-09-02',
      },
    },
    registration: {
      status: 'complete',
      missing: [],
    },
    ...overrides,
  }
}

export function fixtureFrame(overrides: Partial<CameraFrame> = {}): CameraFrame {
  return {
    camera_id: 'ntv-st-johns-sky',
    capture_time: '2026-09-03T12:00:00Z',
    retrieval_time: '2026-09-03T12:00:05Z',
    flags: [],
    image_url: 'https://example.invalid/frame.jpg',
    ...overrides,
  }
}

/** A frame carrying two health flags: `blur` should be named as the refusal,
 *  since it precedes `obstruction` in `HEALTH_FLAGS` order. */
export function fixtureFlaggedFrame(overrides: Partial<CameraFrame> = {}): CameraFrame {
  return fixtureFrame({
    flags: ['blur', 'obstruction'],
    ...overrides,
  })
}

/** A frame whose capture time could not be established. */
export function fixtureCaptureTimeUnknownFrame(overrides: Partial<CameraFrame> = {}): CameraFrame {
  return fixtureFrame({
    capture_time: null,
    flags: ['capture_time_unknown'],
    ...overrides,
  })
}

export function fixtureDisabledMethod(overrides: Partial<CameraMethod> = {}): CameraMethod {
  return {
    name: 'camera_fog_and_visibility_class',
    version: 'camera-class-v0',
    enabled: false,
    refusal: null,
    ...overrides,
  }
}

export function fixtureMethods(): CameraMethod[] {
  return [
    fixtureDisabledMethod({ name: 'camera_fog_and_visibility_class', version: 'camera-class-v0' }),
    fixtureDisabledMethod({ name: 'camera_visibility_bound_from_landmarks', version: 'camera-landmark-bound-v0' }),
    fixtureDisabledMethod({ name: 'camera_daytime_sector_cloud_fraction', version: 'camera-sector-cloud-v0' }),
    fixtureDisabledMethod({ name: 'camera_horizon_fog_bank_presence', version: 'camera-fog-bank-v0' }),
    fixtureDisabledMethod({ name: 'camera_skydome_night_cloud_from_starfield', version: 'camera-starfield-v0' }),
  ]
}

/** A derived field from a disabled method: the distinctive value 0.42 must
 *  never surface in the document, however present it is on this object. */
export function fixtureDerivedFromDisabledMethod(overrides: Partial<CameraDerivedField> = {}): CameraDerivedField {
  return {
    camera_id: 'ntv-st-johns-sky',
    method: 'camera_fog_and_visibility_class',
    field: 'camera_fog_class',
    value: 0.42,
    refusal: null,
    ...overrides,
  }
}

/** A derived field carrying its own refusal, distinct from the method being
 *  disabled - for example a frame health-flag refusal. */
export function fixtureDerivedWithRefusal(overrides: Partial<CameraDerivedField> = {}): CameraDerivedField {
  return {
    camera_id: 'ntv-st-johns-sky',
    method: 'camera_daytime_sector_cloud_fraction',
    field: 'camera_sector_cloud_fraction',
    value: 0.77,
    refusal: 'blur',
    ...overrides,
  }
}
