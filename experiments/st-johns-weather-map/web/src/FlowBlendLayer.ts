/** A MapLibre custom layer that draws the opt-in display interpolation for
 *  one rendered-grid cloud layer: two real retrieved frames, warped toward
 *  each other along a server-derived motion field and cross-dissolved
 *  (advection-corrected interpolation, the radar-nowcasting construction).
 *
 *  Honesty properties, by construction:
 *  - at t=0 and t=1 the output is exactly the real frame, untouched;
 *  - the backward warp uses the negated forward field; the texture's blue
 *    channel is the server's display weight - the support behind that flow -
 *    so cells with no trustworthy motion behind them fall back per-pixel to
 *    a plain linear crossfade;
 *  - with no flow texture at all the shader IS the plain linear crossfade -
 *    which also replaces the old two-stacked-layers compositing
 *    (1-(1-a)(1-b)) with a true linear blend;
 *  - the two warped samples are fused by the time fraction, unless the
 *    selected method's construction is `visibility`, which weighs each by the
 *    server's measured reliability of that frame's own warp so an unreliable
 *    warp is not averaged into a double image with a reliable one; the weights
 *    are normalised and still sum to 1, so every pixel remains a convex
 *    combination of two samples read from the two retrieved frames;
 *  - the `residual-advection` construction adds a served development
 *    envelope AFTER the advection mix: e(t) = t(1-t)(a + b t), with (a, b)
 *    read per cell from the `residual` texture (the server's computed
 *    advection residual, in cloud percent, fitted to a per-request scale).
 *    t(1-t) is zero at both ends, so every retrieved frame still shows
 *    untouched - endpoint exactness is algebra, not a clamp. The result is
 *    clamped to the variable's range [0, 1];
 *  - only the alpha channel is warped and blended: the frames are the
 *    declared white-with-alpha colormap, so alpha IS the scalar, and the
 *    colour stays exactly the colormap's white.
 *
 *  What the envelope CAN do, stated plainly (governing-rule carve-out (d),
 *  owner decision 2026-09-01): between the two real frames it may draw a
 *  value that is in NEITHER frame at that cell. The non-generative
 *  `residual-advection` method serves a gain small enough that the value
 *  stays between the two retrieved values; the `residual-generative` method
 *  does not, and the map discloses that picture as GENERATED and names the
 *  construction. The envelope is never invented here: with no `residual`
 *  texture from the server, or under any other construction, `u_has_envelope`
 *  is 0 and the shader is exactly the advection mix above. Nothing on a data
 *  path (/point, /timeline, /features, stories, readings) reads this layer.
 */

import maplibregl from 'maplibre-gl'
import type { CustomLayerInterface, Map as MapLibreMap } from 'maplibre-gl'

/** The texture slots one layer holds. Two belong to one method each. */
type TextureSlot = 'frame0' | 'frame1' | 'flow' | 'tangents' | 'visibility' | 'residual'

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
  /** Object URL of the pair's per-frame visibility weights (R = frame 0,
   *  G = frame 1), or null when the server serves none - the fusion is then
   *  the symmetric (1-t, t) every other construction uses. */
  visibilityUrl?: string | null
  /** Object URL of the pair's development envelope coefficients (R = a,
   *  G = b, each signed around 128), or null when the served method publishes
   *  none - the shader then draws the advection mix alone. */
  residualUrl?: string | null
  /** The cloud-percent value encoded at channel value 255 in the residual
   *  texture (server header `X-Weather-Flow-Scale`). Divided by 100 to reach
   *  alpha units, since alpha IS the scalar in the white-with-alpha colormap. */
  residualScalePixels?: number
  /** Which construction to evaluate, as the server's method registry named it.
   *  Selected by a uniform: one compiled program serves every branch, so
   *  switching methods mid-scrub never rebuilds a shader. */
  construction?: 'hermite' | 'visibility' | 'residual-advection' | string
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

export const VERTEX_SOURCE = `
attribute vec2 a_position;
attribute vec2 a_uv;
uniform mat4 u_matrix;
varying vec2 v_uv;
void main() {
  v_uv = a_uv;
  gl_Position = u_matrix * vec4(a_position, 0.0, 1.0);
}
`

export const FRAGMENT_SOURCE = `
precision highp float;
varying vec2 v_uv;
uniform sampler2D u_frame0;
uniform sampler2D u_frame1;
uniform sampler2D u_flow;
uniform sampler2D u_tangents; // start knot velocity | end knot velocity
uniform sampler2D u_visibility; // R = frame0 reliability, G = frame1 reliability
uniform sampler2D u_residual; // the pair's development envelope, R = a, G = b, signed around 128
uniform float u_t;
uniform float u_opacity;
uniform float u_has_flow;
uniform float u_has_tangents;
uniform float u_visibility_blend; // 1 = per-pixel visibility fusion branch
uniform float u_has_envelope; // 1 = residual-advection development envelope
uniform float u_envelope_scale; // alpha units encoded at channel value 255
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
  // The two fusion weights. By default they are the time fraction alone, which
  // is what every construction above draws. The visibility branch (Super SloMo,
  // Jiang et al. 2018; softmax splatting, Niklaus & Liu 2020), selected by a
  // uniform so one compiled program still serves every method, scales each by
  // the server's measured reliability of THAT frame's warp and renormalises:
  //   w0 = (1-t) v0, w1 = t v1, then w0 /= w0+w1, w1 /= w0+w1
  // so where one warp is unreliable the other carries the pixel outright
  // instead of the two being averaged into a double image. At v0 == v1 the
  // weights are exactly (1-t, t) and this is the baseline; at either endpoint
  // one weight is zero whatever the reliabilities said, so the branch is
  // endpoint-exact. A zero pair is an off-grid pixel with no measurement, and
  // falls back to the time weights rather than dividing zero by zero. Same
  // arithmetic as VisibilityBlendMethod.composite in ingest/derive/methods.py;
  // the two must change together or the bench ranks a construction the map
  // does not draw.
  float w0 = 1.0 - u_t;
  float w1 = u_t;
  if (u_visibility_blend > 0.5) {
    vec2 visibility = texture2D(u_visibility, v_uv).rg;
    float a0 = (1.0 - u_t) * visibility.r;
    float a1 = u_t * visibility.g;
    float total = a0 + a1;
    if (total > 1e-6) {
      w0 = a0 / total;
      w1 = a1 / total;
    }
  }
  // The two warps, fused by the visibility weights. With the visibility
  // branch off, w0/w1 are (1 - t, t), so this is exactly the symmetric
  // blend it replaced - the same arithmetic, written once.
  float warped =
    w0 * texture2D(u_frame0, v_uv - d0).a +
    w1 * texture2D(u_frame1, v_uv + d1).a;
  float plain = mix(texture2D(u_frame0, v_uv).a, texture2D(u_frame1, v_uv).a, u_t);
  float alpha = mix(plain, warped, advect);
  // The development envelope (residual-advection). The server measured how
  // much cloud formed or dissolved in place - the advection residual - and
  // fitted it per cell to (a, b) so that
  //   e(t) = t (1 - t) (a + b t)
  // is the change drawn between the frames. t(1-t) vanishes at both ends, so
  // every retrieved frame still shows untouched whatever (a, b) say. This is
  // the same parabola ResidualAdvectionMethod.composite evaluates in
  // ingest/derive/methods/residual_advection.py; the two must change together
  // or the bench ranks a construction the map does not draw. The clamp is the
  // variable's physical range, not an endpoint device.
  vec2 ab = (texture2D(u_residual, v_uv).rg * 2.0 - 1.0) * u_envelope_scale;
  float env = u_t * (1.0 - u_t) * (ab.x + ab.y * u_t);
  alpha = clamp(alpha + env * u_has_envelope, 0.0, 1.0);
  alpha *= u_opacity;
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
  /** Why the program is absent, when it is. Null while it compiled and linked.
   *  Read by the panel so a layer that cannot draw says so on the map instead
   *  of vanishing under a disclosure that claims it advected. */
  private programError: string | null = null
  private positionBuffer: WebGLBuffer | null = null
  private uvBuffer: WebGLBuffer | null = null
  private locations: Record<string, WebGLUniformLocation | null> = {}
  private attributes: { position: number; uv: number } = { position: -1, uv: -1 }

  private state: FlowBlendState | null = null
  /** Decoded textures keyed by slot; each remembers the URL it holds. */
  private textures: { frame0?: LoadedTexture; frame1?: LoadedTexture; flow?: LoadedTexture; tangents?: LoadedTexture; residual?: LoadedTexture; visibility?: LoadedTexture } = {}
  private loading = new Map<string, Promise<void>>()

  constructor(id: string) {
    this.id = id
  }

  /** Why this layer cannot draw, or null while it can.
   *
   *  Null before `onAdd` too: nothing has failed yet, it simply has no GL
   *  context. Only a real compile or link failure sets it. */
  get renderError(): string | null {
    return this.programError
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
    // A shader that does not compile still yields a non-null program, and an
    // unchecked one draws nothing while the map goes on disclosing
    // "advection-corrected". That is exactly the control-that-appears-to-do-
    // something the governing rule forbids, so the status is read here and the
    // reason is kept for the panel to disclose rather than swallowed.
    const compile = (kind: number, source: string, label: string): WebGLShader | null => {
      const shader = gl.createShader(kind) as WebGLShader
      gl.shaderSource(shader, source)
      gl.compileShader(shader)
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        this.programError = `${label} shader failed to compile: ${gl.getShaderInfoLog(shader) ?? 'no log'}`
        gl.deleteShader(shader)
        return null
      }
      return shader
    }
    const vertex = compile(gl.VERTEX_SHADER, VERTEX_SOURCE, 'vertex')
    const fragment = compile(gl.FRAGMENT_SHADER, FRAGMENT_SOURCE, 'fragment')
    if (!vertex || !fragment) {
      return
    }
    const program = gl.createProgram() as WebGLProgram
    gl.attachShader(program, vertex)
    gl.attachShader(program, fragment)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      this.programError = `program failed to link: ${gl.getProgramInfoLog(program) ?? 'no log'}`
      gl.deleteProgram(program)
      return
    }
    this.program = program
    this.attributes = {
      position: gl.getAttribLocation(program, 'a_position'),
      uv: gl.getAttribLocation(program, 'a_uv'),
    }
    for (const name of ['u_matrix', 'u_frame0', 'u_frame1', 'u_flow', 'u_tangents', 'u_visibility', 'u_residual', 'u_t', 'u_opacity', 'u_has_flow', 'u_has_tangents', 'u_visibility_blend', 'u_has_envelope', 'u_envelope_scale', 'u_flow_scale_uv', 'u_tangent_scale_uv']) {
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
    if (state.visibilityUrl) this.ensureTexture('visibility', state.visibilityUrl)
    if (state.residualUrl) this.ensureTexture('residual', state.residualUrl)
  }

  private ensureTexture(slot: TextureSlot, url: string): void {
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

  private wantedUrl(slot: TextureSlot): string | null {
    if (!this.state) return null
    if (slot === 'frame0') return this.state.frame0Url
    if (slot === 'frame1') return this.state.frame1Url
    if (slot === 'tangents') return this.state.tangentsUrl
    if (slot === 'visibility') return this.state.visibilityUrl ?? null
    if (slot === 'residual') return this.state.residualUrl ?? null
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
    // The visibility construction needs the server's measured weight pair.
    // Without it there is no reliability to fuse on, so the shader stays on the
    // symmetric (1-t, t) the baseline already draws - one honest rung down,
    // never a reliability guessed at from the frames on the client.
    const visibility = state.visibilityUrl ? this.textures.visibility : undefined
    const visibilityReady = flowReady && !!visibility && visibility.url === state.visibilityUrl
    const visibilityBlend = state.construction === 'visibility' && visibilityReady
    // The envelope is added after the mix, so unlike the branch above it does
    // NOT need the flow texture: the server computed the residual against its
    // own warp, and with no motion at all the envelope still vanishes at both
    // real frames. Without the residual texture the shader draws the mix alone
    // - never an (a, b) invented client-side - and only the construction the
    // server named `residual-advection` may read one at all.
    const residual = state.residualUrl ? this.textures.residual : undefined
    const residualReady =
      state.construction === 'residual-advection' && !!residual && residual.url === state.residualUrl

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
    // Orthogonal to the trajectory: the visibility construction keeps
    // whichever displacement the flow (and its tangents) produced and changes
    // only how the two warped samples are weighed against each other.
    gl.uniform1f(this.locations.u_visibility_blend, visibilityBlend ? 1 : 0)
    gl.uniform1f(this.locations.u_has_envelope, residualReady ? 1 : 0)
    // The served scale is in cloud percent; alpha IS the scalar in [0, 1].
    gl.uniform1f(this.locations.u_envelope_scale, (state.residualScalePixels ?? 0) / 100)
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
    gl.activeTexture(gl.TEXTURE4)
    gl.bindTexture(gl.TEXTURE_2D, (visibilityReady ? visibility : frame0).texture)
    gl.uniform1i(this.locations.u_visibility, 4)
    gl.activeTexture(gl.TEXTURE5)
    gl.bindTexture(gl.TEXTURE_2D, (residualReady ? residual : frame0).texture)
    gl.uniform1i(this.locations.u_residual, 5)

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

/** CPU reference of the shader's development envelope, for tests:
 *  e(t) = t(1-t)(a + b t), the exact expression the fragment shader adds to
 *  the advection mix under the `residual-advection` construction, and the
 *  exact parabola `ResidualAdvectionMethod.composite` evaluates in
 *  ingest/derive/methods/residual_advection.py. `a` and `b` are in alpha
 *  units (cloud percent / 100). e(0) = e(1) = 0 for every (a, b), so every
 *  retrieved frame shows untouched; between them the term is a value in
 *  neither frame, which is why the map discloses it. */
export function envelopeTerm(a: number, b: number, t: number): number {
  return t * (1 - t) * (a + b * t)
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

/** CPU reference of the shader's visibility fusion, for tests: the two blend
 *  weights the fragment shader applies when the `visibility` construction is
 *  selected. `v0`/`v1` are the server's measured reliabilities of the frame-0
 *  and frame-1 warps at this pixel, each in 0..1.
 *
 *  Returns `{ w0, w1 }` summing to 1. `w0(1) = 0` and `w1(0) = 0` whatever the
 *  reliabilities say, so the branch is endpoint-exact; at `v0 === v1` it is
 *  exactly `(1-t, t)`, the symmetric fusion already shipping. A zero pair is an
 *  off-grid pixel with no measurement and falls back to the time weights.
 *  Mirrors VisibilityBlendMethod.composite in ingest/derive/methods.py. */
export function visibilityWeights(
  v0: number,
  v1: number,
  t: number,
): { w0: number; w1: number } {
  const a0 = (1 - t) * v0
  const a1 = t * v1
  const total = a0 + a1
  if (!(total > 1e-6)) return { w0: 1 - t, w1: t }
  return { w0: a0 / total, w1: a1 / total }
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
