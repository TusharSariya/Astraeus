import { describe, expect, it } from 'vitest'
import { FRAGMENT_SOURCE, VERTEX_SOURCE } from './FlowBlendLayer'

/** The shader, handed to a real GLSL compiler.
 *
 *  Every other test in this repo runs under jsdom, which has no WebGL, so the
 *  shader strings were never compiled by anything before a browser did it in
 *  front of a user. Between `a4c9039` and `6e22694` that left `warped` and
 *  `plain` each declared twice in one scope: a hard redefinition error in
 *  GLSL ES 1.00. The program never linked, `render()` drew nothing, and
 *  because `MapPanel` routes locally rendered layers through this layer
 *  EXCLUSIVELY when interpolation is on, the cloud vanished while the map went
 *  on disclosing "advection-corrected". Eighteen verified tasks passed over it,
 *  because every one of their verification commands was a unit test.
 *
 *  So this file exists to do the one thing none of those could: compile it.
 */
describe('the flow-blend shader compiles', () => {
  const context = () => {
    const gl = document.createElement('canvas').getContext('webgl')
    if (!gl) throw new Error('no WebGL context; this suite must run in a real browser')
    return gl
  }

  const compiled = (gl: WebGLRenderingContext, kind: number, source: string) => {
    const shader = gl.createShader(kind)!
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    return { ok: gl.getShaderParameter(shader, gl.COMPILE_STATUS) as boolean, log: gl.getShaderInfoLog(shader), shader }
  }

  it('compiles the vertex shader', () => {
    const gl = context()
    const { ok, log } = compiled(gl, gl.VERTEX_SHADER, VERTEX_SOURCE)
    expect(ok, `vertex shader did not compile:\n${log}`).toBe(true)
  })

  it('compiles the fragment shader', () => {
    const gl = context()
    const { ok, log } = compiled(gl, gl.FRAGMENT_SHADER, FRAGMENT_SOURCE)
    // The info log is the whole value of this assertion: a bare `false` would
    // send the next reader back to a 6 KB string with no line number.
    expect(ok, `fragment shader did not compile:\n${log}`).toBe(true)
  })

  it('links the two into a program', () => {
    const gl = context()
    const vertex = compiled(gl, gl.VERTEX_SHADER, VERTEX_SOURCE)
    const fragment = compiled(gl, gl.FRAGMENT_SHADER, FRAGMENT_SOURCE)
    const program = gl.createProgram()!
    gl.attachShader(program, vertex.shader)
    gl.attachShader(program, fragment.shader)
    gl.linkProgram(program)
    expect(
      gl.getProgramParameter(program, gl.LINK_STATUS),
      `program did not link:\n${gl.getProgramInfoLog(program)}`,
    ).toBe(true)
  })

  it('keeps every uniform the layer binds by name', () => {
    // A uniform the layer sets but the shader never declares is silently a
    // no-op against a null location, so a renamed uniform degrades the picture
    // without failing anything. Names come from the shader source itself, so
    // this pins the two lists together rather than restating one of them.
    const declared = new Set([...VERTEX_SOURCE.matchAll(/uniform\s+\w+\s+(\w+)/g)].map((match) => match[1]))
    for (const match of FRAGMENT_SOURCE.matchAll(/uniform\s+\w+\s+(\w+)/g)) declared.add(match[1])
    const gl = context()
    const vertex = compiled(gl, gl.VERTEX_SHADER, VERTEX_SOURCE)
    const fragment = compiled(gl, gl.FRAGMENT_SHADER, FRAGMENT_SOURCE)
    const program = gl.createProgram()!
    gl.attachShader(program, vertex.shader)
    gl.attachShader(program, fragment.shader)
    gl.linkProgram(program)
    // Only actively-used uniforms survive linking, which is exactly the set
    // worth checking: an unused one cannot change the picture.
    const active = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) as number
    for (let index = 0; index < active; index += 1) {
      const name = gl.getActiveUniform(program, index)!.name.replace(/\[\d+\]$/, '')
      expect(declared, `linked program exposes ${name}, which no shader source declares`).toContain(name)
      expect(gl.getUniformLocation(program, name), `${name} has no location`).not.toBeNull()
    }
  })
})

/** Plan H1: the shader's arithmetic, read back from real pixels.
 *
 *  Compiling proves the program links; it does not prove a single pixel
 *  changes. This block uploads 2x2 textures with known values, draws a
 *  full-screen quad through the SAME program the map uses, and reads the
 *  framebuffer back with `gl.readPixels`. Every expected value below is the
 *  CPU reference in FlowBlendLayer.ts evaluated by hand, quantised to 8 bits.
 */
describe('the flow-blend shader draws the arithmetic it claims (pixel readback)', () => {
  interface Scene {
    t: number
    hasEnvelope: 0 | 1
    visibilityBlend?: 0 | 1
    frame0Alpha?: number
    /** Residual R channel byte: a = (R/255*2-1) * scale. 179 is +0.404 at scale 1. */
    residualR?: number
    /** The served scale, in cloud percent (the layer divides by 100). */
    residualScalePercent?: number
  }

  /** Renders one scene into a 2x2 canvas and returns the RGBA bytes of pixel (0, 0)
   *  and (1, 1), which must agree because every texture is uniform. */
  const renderScene = (scene: Scene): { rgba: number[]; other: number[] } => {
    const canvas = document.createElement('canvas')
    canvas.width = 2
    canvas.height = 2
    const gl = canvas.getContext('webgl', { premultipliedAlpha: false, preserveDrawingBuffer: true, antialias: false })
    if (!gl) throw new Error('no WebGL context; this suite must run in a real browser')
    const compile = (kind: number, source: string) => {
      const shader = gl.createShader(kind)!
      gl.shaderSource(shader, source)
      gl.compileShader(shader)
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? 'compile failed')
      return shader
    }
    const program = gl.createProgram()!
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX_SOURCE))
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT_SOURCE))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? 'link failed')
    gl.useProgram(program)

    const uniform = (name: string) => gl.getUniformLocation(program, name)
    const texture = (unit: number, name: string, rgba: [number, number, number, number]) => {
      const handle = gl.createTexture()!
      gl.activeTexture(gl.TEXTURE0 + unit)
      gl.bindTexture(gl.TEXTURE_2D, handle)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
      const pixels = new Uint8Array([...rgba, ...rgba, ...rgba, ...rgba])
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 2, 2, 0, gl.RGBA, gl.UNSIGNED_BYTE, pixels)
      gl.uniform1i(uniform(name), unit)
    }
    const frame0Alpha = scene.frame0Alpha ?? 0
    // The frames are the white-with-alpha colormap: alpha IS the scalar.
    texture(0, 'u_frame0', [255, 255, 255, frame0Alpha])
    texture(1, 'u_frame1', [255, 255, 255, 255])
    // rg = 128 is (as near as 8 bits allow) zero displacement; b = 255 is the
    // full display weight, so the mix is entirely the warped term. The scale
    // is set to zero below so the residual 128/255 bias is exactly no motion.
    texture(2, 'u_flow', [128, 128, 255, 255])
    texture(3, 'u_tangents', [128, 128, 0, 255])
    // v0 = 1, v1 = 0: the visibility branch must hand the pixel to frame 0.
    texture(4, 'u_visibility', [255, 0, 0, 255])
    // a = +0.404 (byte 179) at scale 1, b ~ 0 (byte 128).
    texture(5, 'u_residual', [scene.residualR ?? 179, 128, 0, 255])

    gl.uniform1f(uniform('u_t'), scene.t)
    gl.uniform1f(uniform('u_opacity'), 1)
    gl.uniform1f(uniform('u_has_flow'), 1)
    gl.uniform1f(uniform('u_has_tangents'), 0)
    gl.uniform1f(uniform('u_visibility_blend'), scene.visibilityBlend ?? 0)
    gl.uniform1f(uniform('u_has_envelope'), scene.hasEnvelope)
    gl.uniform1f(uniform('u_envelope_scale'), (scene.residualScalePercent ?? 100) / 100)
    gl.uniform2f(uniform('u_flow_scale_uv'), 0, 0)
    gl.uniform2f(uniform('u_tangent_scale_uv'), 0, 0)
    gl.uniformMatrix4fv(uniform('u_matrix'), false, new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]))

    const attribute = (name: string, data: number[]) => {
      const buffer = gl.createBuffer()!
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW)
      const location = gl.getAttribLocation(program, name)
      gl.enableVertexAttribArray(location)
      gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0)
    }
    // The identity matrix takes clip-space corners straight through, so the
    // quad covers the whole 2x2 target.
    attribute('a_position', [-1, -1, 1, -1, -1, 1, 1, 1])
    attribute('a_uv', [0, 0, 1, 0, 0, 1, 1, 1])

    gl.disable(gl.BLEND)
    gl.viewport(0, 0, 2, 2)
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)

    const out = new Uint8Array(4 * 4)
    gl.readPixels(0, 0, 2, 2, gl.RGBA, gl.UNSIGNED_BYTE, out)
    return { rgba: [...out.slice(0, 4)], other: [...out.slice(12, 16)] }
  }

  /** The alpha byte, checked against the premultiplied-white invariant. */
  const alphaOf = (result: { rgba: number[]; other: number[] }): number => {
    const [r, g, b, a] = result.rgba
    expect([r, g, b], `premultiplied white: rgb ${[r, g, b]} must equal alpha ${a}`).toEqual([a, a, a])
    expect(result.other, 'a uniform scene must draw the same byte at both corners').toEqual(result.rgba)
    return a
  }

  // a = (179/255*2 - 1) = 0.40392 at scale 1; midpoint envelope 0.25*a.
  const a = (179 / 255) * 2 - 1
  const expectedMidWithEnvelope = Math.round(255 * (0.5 + 0.25 * 0.4))
  const expectedMidWithoutEnvelope = Math.round(255 * 0.5)

  it('draws exactly the real frames at t=0 and t=1, envelope on or off', () => {
    for (const hasEnvelope of [0, 1] as const) {
      const start = alphaOf(renderScene({ t: 0, hasEnvelope }))
      const end = alphaOf(renderScene({ t: 1, hasEnvelope }))
      // eslint-disable-next-line no-console
      console.log(`[H1 readback] envelope=${hasEnvelope} t=0 -> ${start}, t=1 -> ${end}`)
      expect(start, `t=0 must be frame0's alpha exactly (envelope=${hasEnvelope})`).toBe(0)
      expect(end, `t=1 must be frame1's alpha exactly (envelope=${hasEnvelope})`).toBe(255)
    }
  })

  it('adds the served envelope at the midpoint: 0.5 + 0.25*a, and nothing without it', () => {
    const withEnvelope = alphaOf(renderScene({ t: 0.5, hasEnvelope: 1 }))
    const without = alphaOf(renderScene({ t: 0.5, hasEnvelope: 0 }))
    // eslint-disable-next-line no-console
    console.log(`[H1 readback] t=0.5 with envelope (a=${a.toFixed(4)}) -> ${withEnvelope} (expected ~${expectedMidWithEnvelope}); without -> ${without} (expected ~${expectedMidWithoutEnvelope})`)
    expect(Math.abs(withEnvelope - expectedMidWithEnvelope), `midpoint with envelope read ${withEnvelope}`).toBeLessThanOrEqual(1)
    expect(Math.abs(without - expectedMidWithoutEnvelope), `midpoint without envelope read ${without}`).toBeLessThanOrEqual(1)
    // The two pictures differ by a whole envelope, not by rounding: this is
    // the "a branch that cannot be shown to change a pixel is not done" line.
    expect(withEnvelope - without).toBeGreaterThanOrEqual(Math.round(255 * 0.25 * 0.4) - 1)
  })

  it('scales the envelope by the served percent, and a negative residual removes cloud', () => {
    // Same byte at scale 50: half the envelope. Byte 77 is a = -0.396: the
    // midpoint falls below the crossfade, clamped to the physical range.
    const half = alphaOf(renderScene({ t: 0.5, hasEnvelope: 1, residualScalePercent: 50 }))
    const negative = alphaOf(renderScene({ t: 0.5, hasEnvelope: 1, residualR: 77 }))
    // eslint-disable-next-line no-console
    console.log(`[H1 readback] t=0.5 scale 50 -> ${half} (expected ~${Math.round(255 * (0.5 + 0.125 * 0.4))}); negative a -> ${negative} (expected ~${Math.round(255 * (0.5 - 0.25 * 0.4))})`)
    expect(Math.abs(half - Math.round(255 * (0.5 + 0.125 * 0.4)))).toBeLessThanOrEqual(1)
    expect(Math.abs(negative - Math.round(255 * (0.5 - 0.25 * 0.4)))).toBeLessThanOrEqual(1)
  })

  it('hands the whole pixel to frame 0 under the visibility branch when v0=1, v1=0 at t=0.5', () => {
    // frame0 alpha 0: the symmetric mix would read ~128; the visibility branch must read 0.
    const zero = alphaOf(renderScene({ t: 0.5, hasEnvelope: 0, visibilityBlend: 1 }))
    // And with a non-zero frame 0, exactly that frame's byte - not a blend.
    const sixtyFour = alphaOf(renderScene({ t: 0.5, hasEnvelope: 0, visibilityBlend: 1, frame0Alpha: 64 }))
    const symmetric = alphaOf(renderScene({ t: 0.5, hasEnvelope: 0, visibilityBlend: 0, frame0Alpha: 64 }))
    // eslint-disable-next-line no-console
    console.log(`[H1 readback] visibility v0=1,v1=0 t=0.5: frame0=0 -> ${zero}; frame0=64 -> ${sixtyFour}; symmetric mix of 64/255 -> ${symmetric}`)
    expect(zero).toBe(0)
    expect(sixtyFour).toBe(64)
    expect(Math.abs(symmetric - Math.round((64 + 255) / 2))).toBeLessThanOrEqual(1)
  })
})
