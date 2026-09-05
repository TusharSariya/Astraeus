Non-normative research, 2026-09-04. Not a spec or scientific-method admission.

# Band-math renderer contracts

For [Prototype OpenLayers WebGLTile band math against a deck.gl two-texture shader](https://github.com/TusharSariya/Astraeus/issues/57).
Documentation and tagged source inspected; snippets below are implementation
starting points, not browser-tested results. No installation or API mutation
was performed for this note. Map swipe/on-map comparison remains dropped;
image comparison, if retained, belongs in renderer diagnostics.

## OpenLayers: direct numeric COG path

The official example currently pins **ol 10.10.0**. It combines inputs inside
one `GeoTIFF({sources: [...]})`, then addresses the combined bands in one
`WebGLTile` style. This is different from the tile layer's plural `sources`
facility for rendering separate sources. The example combines 10 m and 60 m
inputs; this demonstrates rendering capability, not scientific comparability.
[Official multi-source example](https://openlayers.org/en/latest/examples/cog-math-multisource.html).

Set `normalize: false` for raw-value arithmetic: otherwise per-source statistics
or min/max rescale values. Combined resolution sets must match after a scale.
Band selection is one-based. Nodata can introduce alpha into output bands, so
inspect the resulting mapping before assigning expressions. `interpolate: false`
selects nearest-neighbour resampling. `source.getView()` is a supported promise
for the Map constructor's view.
[GeoTIFF API](https://openlayers.org/en/latest/apidoc/module-ol_source_GeoTIFF-GeoTIFFSource.html).

Example function for two *already audited*, aligned single-band inputs with
no nodata/mask bands. Display range is illustrative and must be supplied by the
caller; this does not register a method or create a persisted result:

```js
// package dependency: "ol": "10.10.0"
import Map from 'ol/Map.js';
import WebGLTile from 'ol/layer/WebGLTile.js';
import GeoTIFF from 'ol/source/GeoTIFF.js';

export function diagnosticDifference(target, firstUrl, secondUrl, range) {
  const source = new GeoTIFF({
    normalize: false,
    interpolate: false,
    sources: [
      {url: firstUrl, bands: [1]},
      {url: secondUrl, bands: [1]}
    ]
  });
  const difference = ['-', ['band', 1], ['band', 2]];
  return new Map({
    target,
    layers: [new WebGLTile({source, style: {
      color: ['interpolate', ['linear'], difference,
        -range, [35, 85, 190, 1],
        0, [245, 245, 245, 1],
        range, [195, 45, 55, 1]]
    }})],
    view: source.getView()
  });
}
```

The expression grammar and interpolated color support are documented in the
[COG color expression example](https://openlayers.org/en/latest/examples/cog-math.html).
Real inputs need explicit validity/alpha masking and verified scale/offset,
unit, grid and temporal interpretation before this function is appropriate.

## deck.gl: custom two-texture path

Pin **@deck.gl/core 9.2.11** and **@deck.gl/layers 9.2.11** for the inspected
implementation below. This is a verified source tag, not a claim that 9.2.11 is
the newest release: the current upgrade guide already discusses 9.3 and its
luma.gl 9.3 dependencies. Since 9.1, custom uniform values use shader modules
and `model.shaderInputs.setProps`; old `model.setUniforms` examples are stale.
[Upgrade guide](https://deck.gl/docs/upgrade-guide).

BitmapLayer has one image prop and one stock sampler. There is no built-in
`image2` or difference mode. Subclassing `getShaders()` and `draw()` can add a
second texture while retaining the inherited mesh, coordinate conversion and
picking. The custom second image prop below uses the same asynchronous image
prop declaration as the parent. The source's filter hook supplies `geometry.uv`.
[BitmapLayer source](https://github.com/visgl/deck.gl/blob/v9.2.11/modules/layers/src/bitmap-layer/bitmap-layer.ts),
[fragment source](https://github.com/visgl/deck.gl/blob/v9.2.11/modules/layers/src/bitmap-layer/bitmap-layer-fragment.ts),
[subclassing guide](https://deck.gl/docs/developer-guide/custom-layers/subclassed-layers).

```js
import {Deck} from '@deck.gl/core';
import {BitmapLayer} from '@deck.gl/layers';

const comparison = {
  name: 'comparison',
  fs: 'uniform sampler2D secondTexture;',
  uniformTypes: {}
};

export class ImageDifferenceLayer extends BitmapLayer {
  static layerName = 'ImageDifferenceLayer';
  static defaultProps = {
    secondImage: {type: 'image', value: null, async: true}
  };
  getShaders() {
    const inherited = super.getShaders();
    return {
      ...inherited,
      modules: [...inherited.modules, comparison],
      inject: {
        ...inherited.inject,
        'fs:DECKGL_FILTER_COLOR': `
          vec4 a = texture(bitmapTexture, geometry.uv);
          vec4 b = texture(secondTexture, geometry.uv);
          color = vec4(abs(a.rgb - b.rgb),
                       min(a.a, b.a) * layer.opacity);
        `
      }
    };
  }
  draw(options) {
    if (!this.props.secondImage || !this.state.model) return;
    this.state.model.shaderInputs.setProps({comparison: {
      secondTexture: this.props.secondImage
    }});
    super.draw(options);
  }
}

export function imageDiagnostic(canvas, image, secondImage, bounds, view) {
  return new Deck({
    canvas,
    initialViewState: view,
    controller: true,
    layers: [new ImageDifferenceLayer({
      id: 'rendered-image-difference', image, secondImage, bounds
    })]
  });
}
```

Use matching dimensions, projection, pixel registration and bounds for the two
images. This snippet performs absolute RGB difference for diagnostics only.
The stock bitmap shader's sampler binding follows a shader module even though
the sampler is not in `uniformTypes`; the added module follows that pattern.
[Bitmap uniform module](https://github.com/visgl/deck.gl/blob/v9.2.11/modules/layers/src/bitmap-layer/bitmap-layer-uniforms.ts).

`new Deck({canvas, initialViewState, controller, layers})` is public and lets
Deck create its device. For manually uploaded numeric textures, use the public
`onDeviceInitialized(device)` callback and `device.createTexture(...)`, or pass
an explicitly created `device`. Do not read protected `deck.device` or internal
layer-manager state. Track and destroy caller-owned textures at teardown.
[Deck API](https://deck.gl/docs/api-reference/core/deck),
[9.2.11 Deck source](https://github.com/visgl/deck.gl/blob/v9.2.11/modules/core/src/lib/deck.ts),
[Texture API](https://luma.gl/docs/api-reference/core/resources/texture).

## Consequences for this prototype

Inference from the interfaces above: numeric COG inputs permit raw band
expressions; provider-coloured PNGs provide display channels. Subtracting two
coloured PNGs cannot recover the original field values, units or signed
physical difference unless a reversible numeric encoding is explicitly known.
A TIFF extension alone does not establish that its samples are scientific
measurements: inspect dtype, bands and metadata.

Conditional requirements for a future numeric benchmark, if the owner retains that scope. These are not approved API additions:

- Supply numeric asset URLs or decoded arrays, dtype, scale/offset, nodata,
  band identity, grid/CRS and pixel registration, plus run/valid-time evidence.
- Establish comparable field semantics and units, temporal support, and a
  declared resampling policy before enabling field subtraction.
- Distinguish renderer diagnostics from a scientific derived-here result.
  The latter requires the accepted comparability contract and registered method.
- Keep missing/unsupported pairs unavailable with a reason; no fabricated
  numeric result or transparent success fallback after load/shader failure.

OpenLayers offers the shorter COG experiment. deck.gl requires an explicit
second texture, custom shader and, for COGs, a decode/tile pipeline outside
BitmapLayer. Browser compilation, nodata propagation, texture orientation and
actual local-pair comparability remain unverified by this research note.
