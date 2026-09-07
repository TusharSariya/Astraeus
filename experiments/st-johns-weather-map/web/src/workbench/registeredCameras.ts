export interface RegisteredCamera {
  id: string; name: string; source_id: string; operator: string; status: string
  latitude: number | null; longitude: number | null; position_surveyed: boolean
  bearing_deg: number | null; horizontal_fov_deg: number | null; vertical_fov_deg: number | null
  geometry_validation: string; registration_complete: boolean; missing_registration: string[]
  declared_retrieval_eligible: boolean; refusal_code: string | null; image_delivery_implemented: false
}
export interface CameraRegistry { version: string; cameras: RegisteredCamera[]; notices: string[] }
export async function loadRegisteredCameras(signal?: AbortSignal): Promise<CameraRegistry> {
  const response = await fetch('/api/experiments/weather/v0/registry/cameras', { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`Camera registry returned ${response.status}`)
  const body = await response.json() as CameraRegistry
  if (!body || typeof body.version !== 'string' || !/^[a-f0-9]{64}$/.test(body.version) || !Array.isArray(body.cameras) || body.cameras.length > 1000 || !Array.isArray(body.notices)) throw new Error('Camera registry is unreadable')
  for (const camera of body.cameras) if (!camera || typeof camera.id !== 'string' || typeof camera.name !== 'string'
    || typeof camera.declared_retrieval_eligible !== 'boolean' || camera.image_delivery_implemented !== false || !Array.isArray(camera.missing_registration)) throw new Error('Camera eligibility is unreadable')
  return body
}
