/** Types for task 6.3: rendering a camera's registration, its frames with
 *  their health flags, and the standing state of the derivation methods that
 *  read those frames.
 *
 *  `CameraRecord` mirrors the registry file shape pinned in the design's
 *  "Camera records" seam (`registry/cameras/<id>.yaml`, validated by
 *  `registry/cameras/schema.json`) - see `registry/cameras/ccg-fort-amherst.yaml`
 *  for a real, `partnership-only` example. `CameraFrame` mirrors
 *  `ingest.cameras.frames.Frame` (`HEALTH_FLAGS`, `CAPTURE_TIME_UNKNOWN`).
 *  `CameraMethod` mirrors a `ingest.derive.registry` entry named in
 *  `CAMERA_METHODS`; `CameraDerivedField` mirrors what
 *  `ingest.cameras.derive.derive` answers for one field. No camera is
 *  admitted and no camera derivation is enabled by this change - this module
 *  renders exactly that: it computes nothing and enables nothing. */

/** The seven health flags a frame's flags may carry, in the order a refusal
 *  reports them (`ingest.cameras.frames.HEALTH_FLAGS`). */
export const HEALTH_FLAGS = [
  'stale_or_duplicate',
  'blur',
  'darkness',
  'exposure',
  'obstruction',
  'lens_water_or_snow',
  'camera_moved',
] as const

export type HealthFlag = (typeof HEALTH_FLAGS)[number]

/** The two states a camera's catalogue entry can carry: not admitted for
 *  retrieval (`partnership-only`), or admitted but with every derivation
 *  still gated on the 30-day validation (`awaiting_validation`). */
export type CameraStatus = 'partnership-only' | 'awaiting_validation'

/** One camera's registration record, as validated by
 *  `registry/cameras/schema.json`. Only the elements this panel renders are
 *  carried here - the full record has more (endpoint, orientation, image,
 *  landmarks, privacy_masks, geometry_validation) that this task does not
 *  show. */
export interface CameraRecord {
  id: string
  name: string
  operator: string
  source_id: string
  status: CameraStatus
  terms: {
    text: string
    url: string
    permission: {
      requested_on: string | null
      requested_from: string
      granted_on: string | null
    }
  }
  registration: {
    status: 'complete' | 'incomplete'
    missing: string[]
  }
}

/** One retrieved frame: `ingest.cameras.frames.Frame`, narrowed to what this
 *  panel shows. `capture_time` is `null` exactly when the frame carries
 *  `CAPTURE_TIME_UNKNOWN` - the panel never invents a time for it. */
export interface CameraFrame {
  camera_id: string
  capture_time: string | null
  retrieval_time: string
  flags: string[]
  image_url: string | null
}

/** One `ingest.derive.registry` entry named in `CAMERA_METHODS`. Every entry
 *  this change registers carries `enabled: false`; `refusal` is set on a
 *  method-level refusal distinct from a per-field one (there is none today,
 *  since registration itself refuses an enabled, unvalidated camera method). */
export interface CameraMethod {
  name: string
  version: string
  enabled: boolean
  refusal: string | null
}

/** What `ingest.cameras.derive.derive` answered for one camera, method and
 *  field. `value` is shown only when `method` names an enabled
 *  `CameraMethod` and `refusal` is `null` - otherwise the row states "no
 *  claim" and never the value, however present it is on this object. */
export interface CameraDerivedField {
  camera_id: string
  method: string
  field: string
  value: unknown
  refusal: string | null
}
