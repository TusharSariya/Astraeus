import { HEALTH_FLAGS, type CameraDerivedField, type CameraFrame, type CameraMethod, type CameraRecord } from './types'

/** The words shown for a camera's catalogue status - distinct text for each,
 *  since the badge's text is the contract this task pins: it must read
 *  exactly `partnership-only` or `awaiting_validation`, never a friendlier
 *  paraphrase that would drift from the status a reader might filter on. */
const STATUS_LABEL: Record<CameraRecord['status'], string> = {
  'partnership-only': 'partnership-only',
  awaiting_validation: 'awaiting_validation',
}

/** The first raised health flag in `HEALTH_FLAGS` order, mirroring
 *  `ingest.cameras.frames.derivation_refusal`: a frame that is both stale
 *  and blurred refuses as `stale_or_duplicate` every time, not by set or
 *  array iteration order. */
function firstRaisedFlag(flags: string[]): string | null {
  for (const flag of HEALTH_FLAGS) {
    if (flags.includes(flag)) return flag
  }
  return null
}

/** One camera's permission request state, in words. Never says "granted"
 *  unless `granted_on` is actually set - an outstanding request is not
 *  permission, and the absence of a request is stated plainly rather than
 *  left as a blank the reader might mistake for "no answer yet". */
function PermissionState({ permission }: { permission: CameraRecord['terms']['permission'] }) {
  if (permission.granted_on) {
    return <p className="camera-permission" data-permission="granted">granted on {permission.granted_on}</p>
  }
  if (permission.requested_on) {
    return (
      <p className="camera-permission" data-permission="requested">
        requested on {permission.requested_on} from {permission.requested_from}
      </p>
    )
  }
  return <p className="camera-permission" data-permission="none">no request sent</p>
}

/** One frame under its camera: capture time or its absence, retrieval time,
 *  and every raised flag as a named chip. A raised flag means every
 *  derivation reading this frame is refused, named here so the refusal is
 *  visible beside the flag that caused it rather than only inferable. */
function FrameRow({ frame, cameraStatus }: { frame: CameraFrame; cameraStatus: CameraStatusForImage }) {
  const refusedBy = firstRaisedFlag(frame.flags)
  const showImage = frame.image_url !== null && cameraStatus !== 'partnership-only'
  return (
    <li className="camera-frame" data-camera-id={frame.camera_id}>
      <span className="camera-frame-capture-time">
        {frame.capture_time ?? 'capture time unknown'}
      </span>
      <span className="camera-frame-retrieval-time">retrieved: {frame.retrieval_time}</span>
      {frame.flags.length > 0 && (
        <ul className="camera-frame-flags">
          {frame.flags.map((flag) => (
            <li key={flag} className="camera-frame-flag-chip" data-flag={flag}>{flag}</li>
          ))}
        </ul>
      )}
      {refusedBy && (
        <p className="camera-frame-refusal">derivations are refused naming {refusedBy}</p>
      )}
      {showImage && <img className="camera-frame-image" src={frame.image_url ?? undefined} alt="" />}
    </li>
  )
}

type CameraStatusForImage = CameraRecord['status']

/** One camera: name, operator, status badge, terms and permission state for
 *  a `partnership-only` camera, missing elements for an incomplete
 *  registration, and its frames. */
function CameraSection({ camera, frames }: { camera: CameraRecord; frames: CameraFrame[] }) {
  const cameraFrames = frames.filter((frame) => frame.camera_id === camera.id)
  return (
    <section aria-label={camera.name} className="camera-section" data-camera-id={camera.id}>
      <header>
        <h3>{camera.name}</h3>
        <p className="camera-operator">{camera.operator}</p>
        <span className="camera-status-badge" data-status={camera.status}>{STATUS_LABEL[camera.status]}</span>
      </header>

      {camera.status === 'partnership-only' && (
        <div className="camera-terms">
          <p className="camera-terms-text">{camera.terms.text}</p>
          <PermissionState permission={camera.terms.permission} />
        </div>
      )}

      {camera.registration.status === 'incomplete' && (
        <div className="camera-registration-incomplete" data-registration="incomplete">
          <p>incomplete registration; missing:</p>
          <ul>
            {camera.registration.missing.map((element) => (
              <li key={element} data-missing={element}>{element}</li>
            ))}
          </ul>
        </div>
      )}

      <ul className="camera-frames" aria-label={`${camera.name} frames`}>
        {cameraFrames.map((frame) => (
          <FrameRow key={`${frame.camera_id}-${frame.capture_time ?? frame.retrieval_time}`} frame={frame} cameraStatus={camera.status} />
        ))}
      </ul>
    </section>
  )
}

/** The registry of camera derivation methods: name, version, and the
 *  disabled statement for every method that is not yet validated - which
 *  today is every method (no camera derivation is enabled by this change). */
function MethodRegistry({ methods }: { methods: CameraMethod[] }) {
  return (
    <section aria-label="Camera methods" className="camera-methods">
      <h3>Camera methods</h3>
      <ul>
        {methods.map((method) => (
          <li key={method.name} data-method={method.name} data-enabled={String(method.enabled)}>
            <span className="camera-method-name">{method.name}</span>
            <span className="camera-method-version">{method.version}</span>
            {!method.enabled && (
              <span className="camera-method-disabled">disabled, awaiting validation</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** One derived field's row: a value only when its method is enabled and it
 *  carries no refusal; otherwise "no claim", naming the method and the
 *  refusal, and never the value - whatever value the object happens to
 *  carry. This is the gate the whole task exists to enforce: an interface
 *  never presents a camera-derived claim from a disabled method. */
function DerivedFieldRow({ derived, methods }: { derived: CameraDerivedField; methods: CameraMethod[] }) {
  const method = methods.find((candidate) => candidate.name === derived.method)
  const methodEnabled = method?.enabled ?? false
  const claimShown = methodEnabled && derived.refusal === null

  if (claimShown) {
    return (
      <li className="camera-derived-field camera-derived-field-present" data-field={derived.field} data-camera-id={derived.camera_id}>
        <span className="camera-derived-field-name">{derived.field}</span>
        <span className="camera-derived-field-value">{String(derived.value)}</span>
      </li>
    )
  }

  const refusal = derived.refusal ?? (method ? 'awaiting_validation' : 'unregistered_method')
  return (
    <li className="camera-derived-field camera-derived-field-absent" data-field={derived.field} data-camera-id={derived.camera_id}>
      <span className="camera-derived-field-name">{derived.field}</span>
      <span className="camera-derived-field-no-claim">
        no claim: method {derived.method} - {refusal}
      </span>
    </li>
  )
}

/** Cameras, their frames with health flags, the camera-method registry and
 *  the derived fields those methods answered - or refused. This component
 *  computes nothing and enables nothing: it renders exactly what the
 *  registry, the frame store and the derivation gate already decided. */
export function CameraPanel({
  cameras,
  frames,
  methods,
  derived,
}: {
  cameras: CameraRecord[]
  frames: CameraFrame[]
  methods: CameraMethod[]
  derived: CameraDerivedField[]
}) {
  return (
    <section aria-label="Cameras" className="camera-panel">
      <section aria-label="Camera registry">
        <h2>Cameras</h2>
        {cameras.map((camera) => (
          <CameraSection key={camera.id} camera={camera} frames={frames} />
        ))}
      </section>

      <MethodRegistry methods={methods} />

      <section aria-label="Camera-derived fields">
        <h3>Camera-derived fields</h3>
        <ul>
          {derived.map((field) => (
            <DerivedFieldRow key={`${field.camera_id}-${field.method}-${field.field}`} derived={field} methods={methods} />
          ))}
        </ul>
      </section>
    </section>
  )
}
