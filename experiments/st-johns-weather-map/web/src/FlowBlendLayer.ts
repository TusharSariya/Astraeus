/** A MapLibre custom layer that draws the opt-in display interpolation for
 *  one rendered-grid cloud layer: two real retrieved frames, warped toward
 *  each other along a server-derived motion field and cross-dissolved
 *  (advection-corrected interpolation, the radar-nowcasting construction).
 *
 *  Honesty properties, by construction:
 *  - at t=0 and t=1 the output is exactly the real frame, untouched;
 *  - the backward warp uses the negated forward field; the texture's blue
 *    channel is the server's display weight - how well the two frames warped
 *    to the midpoint agree, gated by the support behind that flow - so cells
 *    where cloud grew or decayed in place rather than moved, and cells with
 *    no trustworthy motion behind them, fall back per-pixel to a plain
 *    linear crossfade;
 *  - with no flow texture at all the shader IS the plain linear crossfade -
 *    which also replaces the old two-stacked-layers compositing
 *    (1-(1-a)(1-b)) with a true linear blend;
 *  - only the alpha channel is warped and blended: the frames are the
 *    declared white-with-alpha colormap, so alpha IS the scalar, and the
 *    colour stays exactly the colormap's white.
 *
 *  The layer never invents pixels outside its inputs: every sample is read
 *  from one of the two retrieved frame textures.
 */

import maplibregl from 'maplibre-gl'
import type { CustomLayerInterface, Map as MapLibreMap } from 'maplibre-gl'

export interface FlowBlendState {
  /** Object URLs of the two real frame PNGs (earlier, later). */
  frame0Url: string
  frame1Url: string
  /** Object URL of the flow texture, or null for a plain crossfade. */
  flowUrl: string | null
  /** Max displacement in output pixels encoded at value 255 (server header). */
  flowScalePixels: number
  /** Object URL of the pair's Hermite tangent texture (start knot velocity in
   *  the left half, end knot in the right), or null for linear advection. */
  tangentsUrl: string | null
  tangentsScalePixels: number
  /** The shared request extent of frames and flow. */
  bounds: { west: number; south: number; east: number; north: number }
  /** Pixel size of the frame textures (for pixels -> uv conversion). */
  widthPx: number
  heightPx: number
  /** Interpolation fraction: 0 = earlier frame, 1 = later frame. */
  t: number
  /** The layer's user opacity. */
  opacity: number
}

const VERTEX_SOURCE = `
attribute vec2 a_position;
attribute vec2 a_uv;
uniform mat4 u_matrix;
varying vec2 v_uv;
void main() {
  v_uv = a_uv;
  gl_Position = u_matrix * vec4(a_position, 0.0, 1.0);
}
`

const FRAGMENT_SOURCE = `
precision highp float;
varying vec2 v_uv;
uniform sampler2D u_frame0;
uniform sampler2D u_frame1;
uniform sampler2D u_flow;
uniform sampler2D u_tangents; // start knot velocity | end knot velocity
uniform float u_t;
uniform float u_opacity;
uniform float u_has_flow;
uniform float u_has_tangents;
uniform vec2 u_flow_scale_uv; // max displacement, in uv units per axis
uniform vec2 u_tangent_scale_uv;
void main() {
  vec4 flow_sample = texture2D(u_flow, v_uv);
  vec2 flow_uv = (flow_sample.rg * 2.0 - 1.0) * u_flow_scale_uv;
  // Blue is the server's display weight: 1 advects, 0 crossfades.
  float advect = flow_sample.b * u_has_flow;
  // Displacement from the earlier frame. Linear advection (d0 = t*F) unless
  // the pair's Hermite tangents are held, then the C1 cubic
  // d0 = vs*t + (3F - 2vs - ve)*t^2 + (-2F + vs + ve)*t^3, whose velocity
  // matches the neighbouring segments at the real frames. d1 = F - d0 keeps
  // both constructions endpoint-exact: d0(0) = 0 and d1(1) = 0.
  vec2 d0 = u_t * flow_uv;
  if (u_has_tangents > 0.5) {
    vec2 half_uv = vec2(v_uv.x * 0.5, v_uv.y);
    vec2 vs = (texture2D(u_tangents, half_uv).rg * 2.0 - 1.0) * u_tangent_scale_uv;
    vec2 ve = (texture2D(u_tangents, half_uv + vec2(0.5, 0.0)).rg * 2.0 - 1.0) * u_tangent_scale_uv;
    vec2 b = 3.0 * flow_uv - 2.0 * vs - ve;
    vec2 c = -2.0 * flow_uv + vs + ve;
    d0 = vs * u_t + b * u_t * u_t + c * u_t * u_t * u_t;
  }
  vec2 d1 = flow_uv - d0;
  float warped = mix(
    texture2D(u_frame0, v_uv - d0).a,
    texture2D(u_frame1, v_uv + d1).a,
    u_t
  );
  float plain = mix(texture2D(u_frame0, v_uv).a, texture2D(u_frame1, v_uv).a, u_t);
  float alpha = mix(plain, warped, advect) * u_opacity;
  gl_FragColor = vec4(alpha, alpha, alpha, alpha); // premultiplied white
}
`

interface LoadedTexture {
  texture: WebGLTexture
  url: string
}

export class FlowBlendLayer implements CustomLayerInterface {
  readonly id: string
  readonly type = 'custom' as const
  readonly renderingMode = '2d' as const

  private map: MapLibreMap | null = null
  private gl: WebGLRenderingContext | WebGL2RenderingContext | null = null
  private program: WebGLProgram | null = null
  private positionBuffer: WebGLBuffer | null = null
  private uvBuffer: WebGLBuffer | null = null
  private locations: Record<string, WebGLUniformLocation | null> = {}
  private attributes: { position: number; uv: number } = { position: -1, uv: -1 }

  private state: FlowBlendState | null = null
  /** Decoded textures keyed by slot; each remembers the URL it holds. */
  private textures: { frame0?: LoadedTexture; frame1?: LoadedTexture; flow?: LoadedTexture; tangents?: LoadedTexture } = {}
  private loading = new Map<string, Promise<void>>()

  constructor(id: string) {
    this.id = id
  }

  /** New inputs. Safe before onAdd (kept pending) and cheap when only `t`
   *  or opacity changed. */
  update(state: FlowBlendState): void {
    this.state = state
    if (this.gl) {
      this.ensureTextures()
      this.map?.triggerRepaint()
    }
  }

  onAdd(map: MapLibreMap, gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    this.map = map
    this.gl = gl
    const compile = (kind: number, source: string): WebGLShader => {
      const shader = gl.createShader(kind) as WebGLShader
      gl.shaderSource(shader, source)
      gl.compileShader(shader)
      return shader
    }
    const program = gl.createProgram() as WebGLProgram
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX_SOURCE))
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT_SOURCE))
    gl.linkProgram(program)
    this.program = program
    this.attributes = {
      position: gl.getAttribLocation(program, 'a_position'),
      uv: gl.getAttribLocation(program, 'a_uv'),
    }
    for (const name of ['u_matrix', 'u_frame0', 'u_frame1', 'u_flow', 'u_tangents', 'u_t', 'u_opacity', 'u_has_flow', 'u_has_tangents', 'u_flow_scale_uv', 'u_tangent_scale_uv']) {
      this.locations[name] = gl.getUniformLocation(program, name)
    }
    this.positionBuffer = gl.createBuffer()
    this.uvBuffer = gl.createBuffer()
    if (this.uvBuffer) {
      gl.bindBuffer(gl.ARRAY_BUFFER, this.uvBuffer)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW)
    }
    this.ensureTextures()
  }

  onRemove(): void {
    const gl = this.gl
    if (gl) {
      for (const held of Object.values(this.textures)) if (held) gl.deleteTexture(held.texture)
      if (this.program) gl.deleteProgram(this.program)
      if (this.positionBuffer) gl.deleteBuffer(this.positionBuffer)
      if (this.uvBuffer) gl.deleteBuffer(this.uvBuffer)
    }
    this.textures = {}
    this.loading.clear()
    this.program = null
    this.gl = null
    this.map = null
  }

  private ensureTextures(): void {
    const state = this.state
    if (!state || !this.gl) return
    this.ensureTexture('frame0', state.frame0Url)
    this.ensureTexture('frame1', state.frame1Url)
    if (state.flowUrl) this.ensureTexture('flow', state.flowUrl)
    if (state.tangentsUrl) this.ensureTexture('tangents', state.tangentsUrl)
  }

  private ensureTexture(slot: 'frame0' | 'frame1' | 'flow' | 'tangents', url: string): void {
    const gl = this.gl
    if (!gl) return
    if (this.textures[slot]?.url === url || this.loading.has(`${slot}|${url}`)) return
    const image = new Image()
    const promise = new Promise<void>((resolve) => {
      image.onload = () => {
        // The layer may have moved on (or been removed) while decoding.
        if (!this.gl || this.wantedUrl(slot) !== url) {
          resolve()
          return
        }
        const texture = this.gl.createTexture() as WebGLTexture
        this.gl.bindTexture(this.gl.TEXTURE_2D, texture)
        this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_WRAP_S, this.gl.CLAMP_TO_EDGE)
        this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_WRAP_T, this.gl.CLAMP_TO_EDGE)
        this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MIN_FILTER, this.gl.LINEAR)
        this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MAG_FILTER, this.gl.LINEAR)
        this.gl.texImage2D(this.gl.TEXTURE_2D, 0, this.gl.RGBA, this.gl.RGBA, this.gl.UNSIGNED_BYTE, image)
        const previous = this.textures[slot]
        if (previous) this.gl.deleteTexture(previous.texture)
        this.textures[slot] = { texture, url }
        this.map?.triggerRepaint()
        resolve()
      }
      image.onerror = () => resolve()
    }).finally(() => this.loading.delete(`${slot}|${url}`))
    this.loading.set(`${slot}|${url}`, promise)
    image.src = url
  }

  private wantedUrl(slot: 'frame0' | 'frame1' | 'flow' | 'tangents'): string | null {
    if (!this.state) return null
    if (slot === 'frame0') return this.state.frame0Url
    if (slot === 'frame1') return this.state.frame1Url
    if (slot === 'tangents') return this.state.tangentsUrl
    return this.state.flowUrl
  }

  render(
    gl: WebGLRenderingContext | WebGL2RenderingContext,
    options: { defaultProjectionData?: { mainMatrix: ArrayLike<number> }; modelViewProjectionMatrix?: ArrayLike<number> },
  ): void {
    // Mercator-only custom layer: the vertices are unit-mercator coordinates
    // (MercatorCoordinate.fromLngLat), and the matrix that takes THOSE to
    // clip space is defaultProjectionData.mainMatrix. MapLibre's
    // modelViewProjectionMatrix operates on world-pixel coordinates
    // (mercator times worldSize) - feeding unit mercator through it puts the
    // quad tens of thousands of units off screen, silently: exactly the
    // never-drawing bug this line once shipped with (found live 2026-08-31).
    const matrix = options.defaultProjectionData?.mainMatrix ?? options.modelViewProjectionMatrix
    if (!matrix) return
    const state = this.state
    const frame0 = this.textures.frame0
    const frame1 = this.textures.frame1
    // Draw only a complete pair whose textures match the wanted frames; until
    // then the previous MapLibre-drawn frame (kept by the panel) stays up.
    if (!state || !this.program || !frame0 || !frame1) return
    if (frame0.url !== state.frame0Url || frame1.url !== state.frame1Url) return
    const flow = state.flowUrl ? this.textures.flow : undefined
    const flowReady = !!flow && flow.url === state.flowUrl
    const tangents = state.tangentsUrl ? this.textures.tangents : undefined
    // Tangents only ever refine a held flow: without the flow texture there
    // is no F to build the cubic on, so the shader stays on its crossfade.
    const tangentsReady = flowReady && !!tangents && tangents.url === state.tangentsUrl

    const corners = [
      maplibregl.MercatorCoordinate.fromLngLat({ lng: state.bounds.west, lat: state.bounds.north }),
      maplibregl.MercatorCoordinate.fromLngLat({ lng: state.bounds.east, lat: state.bounds.north }),
      maplibregl.MercatorCoordinate.fromLngLat({ lng: state.bounds.west, lat: state.bounds.south }),
      maplibregl.MercatorCoordinate.fromLngLat({ lng: state.bounds.east, lat: state.bounds.south }),
    ]
    const positions = new Float32Array(corners.flatMap((corner) => [corner.x, corner.y]))

    gl.useProgram(this.program)
    gl.uniformMatrix4fv(this.locations.u_matrix, false, Float32Array.from(matrix as ArrayLike<number>))
    gl.uniform1f(this.locations.u_t, Math.max(0, Math.min(1, state.t)))
    gl.uniform1f(this.locations.u_opacity, Math.max(0, Math.min(1, state.opacity)))
    gl.uniform1f(this.locations.u_has_flow, flowReady ? 1 : 0)
    gl.uniform1f(this.locations.u_has_tangents, tangentsReady ? 1 : 0)
    gl.uniform2f(
      this.locations.u_flow_scale_uv,
      state.flowScalePixels / Math.max(1, state.widthPx),
      state.flowScalePixels / Math.max(1, state.heightPx),
    )
    gl.uniform2f(
      this.locations.u_tangent_scale_uv,
      state.tangentsScalePixels / Math.max(1, state.widthPx),
      state.tangentsScalePixels / Math.max(1, state.heightPx),
    )

    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, frame0.texture)
    gl.uniform1i(this.locations.u_frame0, 0)
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, frame1.texture)
    gl.uniform1i(this.locations.u_frame1, 1)
    gl.activeTexture(gl.TEXTURE2)
    gl.bindTexture(gl.TEXTURE_2D, (flowReady ? flow : frame0).texture)
    gl.uniform1i(this.locations.u_flow, 2)
    gl.activeTexture(gl.TEXTURE3)
    gl.bindTexture(gl.TEXTURE_2D, (tangentsReady ? tangents : frame0).texture)
    gl.uniform1i(this.locations.u_tangents, 3)

    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(this.attributes.position)
    gl.vertexAttribPointer(this.attributes.position, 2, gl.FLOAT, false, 0, 0)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.uvBuffer)
    gl.enableVertexAttribArray(this.attributes.uv)
    gl.vertexAttribPointer(this.attributes.uv, 2, gl.FLOAT, false, 0, 0)

    gl.enable(gl.BLEND)
    gl.blendFuncSeparate(gl.ONE, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
  }
}

/** CPU reference of the shader's Hermite displacement, for tests: the exact
 *  cubic the fragment shader evaluates per component. `flow` is the pair's
 *  displacement F, `vStart`/`vEnd` the knot velocities; returns d0(t), the
 *  displacement from the earlier frame (d1(t) = F - d0(t)).
 *  d0(0) = 0 and d0(1) = F by construction; at vStart = vEnd = F it is
 *  exactly the linear advection t*F. */
export function hermiteDisplacement(flow: number, vStart: number, vEnd: number, t: number): number {
  const b = 3 * flow - 2 * vStart - vEnd
  const c = -2 * flow + vStart + vEnd
  return vStart * t + b * t * t + c * t * t * t
}

/** CPU reference of the shader's blend, for tests: the exact formula the
 *  fragment shader applies to one pixel's alpha values. */
export function blendReference(
  alpha0: number,
  alpha1: number,
  warpedAlpha0: number,
  warpedAlpha1: number,
  t: number,
  confidence: number,
): number {
  const plain = alpha0 * (1 - t) + alpha1 * t
  const warped = warpedAlpha0 * (1 - t) + warpedAlpha1 * t
  return plain * (1 - confidence) + warped * confidence
}
