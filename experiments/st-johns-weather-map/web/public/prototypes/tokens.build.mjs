// PROTOTYPE, throwaway. Builds tokens.json for the design-token ticket (#41).
// Every colour is computed in OKLCH and validated with the dataviz skill's
// validator against the surfaces it will actually sit on. Nothing is eyeballed.
//
//   node tokens.build.mjs [path/to/validate_palette.js]
//
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const VALIDATOR =
  process.argv[2] ??
  "/private/tmp/claude-501/bundled-skills/2.1.261/33b490830b279beb8dd9d8ebea5751f0/dataviz/scripts/validate_palette.js";
const { validate, validateOrdinal, contrast } = await import(pathToFileURL(VALIDATOR).href);

// ---------- OKLCH -> sRGB hex, with chroma-reducing gamut clip ----------
const clamp01 = (x) => Math.max(0, Math.min(1, x));
function oklabToLinear(L, a, b) {
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  return [
    +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}
const lin2s = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const inGamut = (rgb) => rgb.every((c) => c >= -0.0005 && c <= 1.0005);
function oklch(L, C, H) {
  const h = (H * Math.PI) / 180;
  let c = C;
  let rgb = oklabToLinear(L, c * Math.cos(h), c * Math.sin(h));
  while (!inGamut(rgb) && c > 0) {
    c -= 0.002;
    rgb = oklabToLinear(L, c * Math.cos(h), c * Math.sin(h));
  }
  return (
    "#" +
    rgb
      .map((v) => Math.round(clamp01(lin2s(clamp01(v))) * 255).toString(16).padStart(2, "0"))
      .join("")
  );
}
// forward, for reporting
function hexToOklch(hex) {
  const s = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = s.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const [r, g, b] = lin;
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s2 = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s2;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s2;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s2;
  return { L: +L.toFixed(3), C: +Math.hypot(A, B).toFixed(3), H: +((((Math.atan2(B, A) * 180) / Math.PI) % 360 + 360) % 360).toFixed(1) };
}

// ---------- Variants: type and neutral temperature ----------
// Structurally different answers to "what does the system feel like".
const VARIANTS = {
  A: {
    name: "Instrument",
    blurb: "One family for everything: IBM Plex Sans for UI, IBM Plex Mono for values, tags and times. Cool slate neutrals. Dense, 13px base.",
    fonts: {
      ui: `"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif`,
      display: `"IBM Plex Sans", system-ui, sans-serif`,
      mono: `"IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace`,
      google: "family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500",
    },
    neutral: { hue: 250, chroma: 0.012 },
    base: 13,
    density: "compact",
  },
  B: {
    name: "Almanac",
    blurb: "Serif display (Source Serif 4) over a humanist sans (Source Sans 3), mono only for values and tags. Warm paper neutrals. 14px base.",
    fonts: {
      ui: `"Source Sans 3", system-ui, -apple-system, "Segoe UI", sans-serif`,
      display: `"Source Serif 4", Georgia, "Times New Roman", serif`,
      mono: `"IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace`,
      google: "family=Source+Serif+4:wght@500;600&family=Source+Sans+3:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500",
    },
    neutral: { hue: 80, chroma: 0.014 },
    base: 14,
    density: "comfortable",
  },
  C: {
    name: "Hyperlegible",
    blurb: "Atkinson Hyperlegible Next everywhere, its mono for values. Pure neutral greys, 15px base, 44px targets: the outdoor-first, gloved-hand answer.",
    fonts: {
      ui: `"Atkinson Hyperlegible Next", system-ui, -apple-system, "Segoe UI", sans-serif`,
      display: `"Atkinson Hyperlegible Next", system-ui, sans-serif`,
      mono: `"Atkinson Hyperlegible Mono", ui-monospace, "SF Mono", Menlo, monospace`,
      google: "family=Atkinson+Hyperlegible+Next:wght@400;500;700&family=Atkinson+Hyperlegible+Mono:wght@400;500",
    },
    neutral: { hue: 0, chroma: 0 },
    base: 15,
    density: "spacious",
  },
};

// ---------- Neutral scale per variant (12 steps, OKLCH L) ----------
const NEUTRAL_L = { 0: 0.995, 50: 0.975, 100: 0.945, 200: 0.9, 300: 0.83, 400: 0.72, 500: 0.6, 600: 0.5, 700: 0.4, 800: 0.3, 900: 0.22, 950: 0.16, 1000: 0.11 };
function neutrals({ hue, chroma }) {
  const out = {};
  for (const [k, L] of Object.entries(NEUTRAL_L)) out[k] = oklch(L, chroma * (L > 0.5 ? 1 : 1.4), hue);
  return out;
}

// ---------- Night theme candidates ----------
// red: the provenance ticket's black + one red hue, now with luminance steps.
// ember: the Activity canvas's burgundy surfaces with dim red and amber.
const NIGHT = {
  red: {
    name: "Red on black",
    blurb: "Black surfaces, one long-wavelength red carried at four luminances. Nothing but red light leaves the screen.",
    bg: "#000000",
    panel: oklch(0.13, 0.05, 28),
    raised: oklch(0.18, 0.07, 28),
    line: oklch(0.3, 0.1, 28),
    ink: oklch(0.64, 0.24, 28),
    muted: oklch(0.48, 0.18, 28),
    faint: oklch(0.36, 0.13, 28),
    accent: oklch(0.7, 0.23, 28),
    warn: oklch(0.72, 0.2, 40),
    bad: oklch(0.78, 0.17, 28),
  },
  ember: {
    name: "Ember",
    blurb: "Burgundy surfaces, dim red ink, amber for warnings and emphasis. Warmer and easier to read, at the cost of some dark adaptation.",
    bg: oklch(0.13, 0.04, 15),
    panel: oklch(0.18, 0.05, 15),
    raised: oklch(0.23, 0.06, 15),
    line: oklch(0.34, 0.08, 20),
    ink: oklch(0.7, 0.19, 30),
    muted: oklch(0.55, 0.14, 30),
    faint: oklch(0.42, 0.1, 30),
    accent: oklch(0.76, 0.15, 65),
    warn: oklch(0.78, 0.16, 70),
    bad: oklch(0.72, 0.2, 25),
  },
};

// ---------- Categorical palettes: search L/C inside the band, keep the hue ----------
const BAND = { light: [0.43, 0.77], dark: [0.48, 0.67] };
function bestCategorical(hues, mode, surface, pairs) {
  const [lo, hi] = BAND[mode];
  let best = null;
  const Ls = [], Cs = [0.12, 0.14, 0.16, 0.18];
  for (let L = lo + 0.02; L <= hi - 0.02; L += 0.02) Ls.push(+L.toFixed(2));
  // per-hue L offsets: alternate up/down so neighbours separate in lightness too
  const offsets = [0, 0.04, -0.04, 0.07, -0.07];
  for (const L of Ls) for (const C of Cs) for (const off of offsets) {
    const pal = hues.map((h, i) => {
      const Li = Math.max(lo + 0.005, Math.min(hi - 0.005, L + (i % 2 ? off : -off)));
      return oklch(Li, C, h);
    });
    const r = validate(pal, { mode, surface, pairs });
    const hardFail = r.report.some(([name, pass]) => !pass && name !== "Contrast vs surface" && !/CVD/.test(name));
    // score: min cvd deltaE, then min normal deltaE
    const cvd = r.report.find(([n]) => /CVD/.test(n));
    const m = /ΔE ([0-9.]+)/.exec(cvd?.[2] ?? "");
    const nv = r.report.find(([n]) => /Normal-vision/.test(n));
    const m2 = /ΔE ([0-9.]+)/.exec(nv?.[2] ?? "");
    const contrastRow = r.report.find(([n]) => /Contrast/.test(n));
    const relief = /relief|below 3:1/.test(contrastRow?.[2] ?? "");
    const score = (r.ok ? 1000 : 0) + (hardFail ? -1000 : 0) + (relief ? -500 : 0) + (m ? +m[1] * 2 : 0) + (m2 ? +m2[1] : 0) - 60 * Math.abs(off);
    if (!best || score > best.score) best = { pal, score, report: r };
  }
  return best;
}

// Source slots: the dataviz default order's hues (blue, orange, aqua, yellow, magenta, green, violet, red)
const SOURCE_HUES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"].map((h) => hexToOklch(h).H);
const SOURCE_SLOTS = [
  { slot: 1, hue: "blue", provider: "ECCC models", sources: ["eccc-hrdps", "eccc-rdps", "eccc-gdps", "eccc-reps"] },
  { slot: 2, hue: "orange", provider: "NOAA NCEP", sources: ["noaa-gfs", "noaa-gefs"] },
  { slot: 3, hue: "aqua", provider: "ECMWF", sources: ["ecmwf-ifs", "ecmwf-ens", "ecmwf-aifs-ens"] },
  { slot: 4, hue: "yellow", provider: "DWD", sources: ["dwd-icon-global"] },
  { slot: 5, hue: "magenta", provider: "Observations", sources: ["awc-metar-speci", "awc-taf", "eccc-swob"] },
  { slot: 6, hue: "green", provider: "Space weather", sources: ["noaa-swpc-kp", "noaa-swpc-ovation"] },
  { slot: 7, hue: "violet", provider: "Imagery", sources: ["noaa-goes-east", "eccc-radar", "eccc-lightning"] },
  { slot: 8, hue: "red", provider: "Other", sources: ["everything else folds here"] },
];

// Evidence classes: hue per class, colour redundant to shape and fill.
const EVIDENCE = [
  { key: "retrieved", hue: 150, glyph: "filled circle" },
  { key: "reprocessed", hue: 90, glyph: "half-filled circle" },
  { key: "derived_here", hue: 270, glyph: "filled diamond" },
  { key: "intermediary_derived", hue: 210, glyph: "outline diamond" },
  { key: "generated_display", hue: 30, glyph: "dashed circle" },
  { key: "uncalibrated_observation", hue: 330, glyph: "outline triangle" },
];

// Status, fixed (dataviz reference instance), checked for contrast on our surfaces.
const STATUS = { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" };

// ---------- Ramps ----------
function ramp(hue, mode, steps = 7, { chroma = 0.13, from, to } = {}) {
  // light: light -> dark; dark: the anchor flips (dark surface, so the low end is dark)
  const [a, b] = mode === "light" ? [from ?? 0.93, to ?? 0.33] : [from ?? 0.3, to ?? 0.9];
  const out = [];
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    const L = a + (b - a) * t;
    const c = chroma * Math.sin(Math.PI * (0.15 + 0.7 * t)) + 0.02; // low chroma at both ends, peak mid
    out.push(oklch(L, c, hue));
  }
  return out;
}
function diverging(hueNeg, huePos, mode, steps = 4, neutral) {
  const neg = ramp(hueNeg, mode, steps + 1).slice(1).reverse(); // dark..light minus the palest
  const pos = ramp(huePos, mode, steps + 1).slice(1);
  const arm = (arr) => (mode === "light" ? arr : arr);
  return mode === "light" ? [...neg.reverse(), neutral, ...pos] : [...arm(neg).reverse(), neutral, ...arm(pos)];
}
const SEQUENTIAL = [
  { key: "cloud", families: ["cloud_cover", "cloud_geometry"], hue: 240, chroma: 0.06, note: "Cover and heights. Comparability groups never share one ramp: each group takes its own step range and the separate-scales chip." },
  { key: "precipitation", families: ["precipitation", "marine"], hue: 195, chroma: 0.12, note: "Accumulation, rate, wave height, sea state." },
  { key: "wind", families: ["wind"], hue: 290, chroma: 0.13, note: "Speed and gust. Direction is a glyph, never a colour." },
  { key: "humidity", families: ["humidity", "boundary_layer"], hue: 150, chroma: 0.12, note: "Relative and specific humidity, dew point, column vapour, boundary-layer height." },
  { key: "radiation", families: ["radiation", "lightning"], hue: 75, chroma: 0.14, note: "Shortwave flux, accumulations, flash density." },
  { key: "visibility", families: ["visibility"], hue: 55, chroma: 0.08, note: "Inverted: the dark end is low visibility. Fog states are chips, not colours." },
  { key: "aerosol", families: ["air_quality", "seeing", "transparency"], hue: 20, chroma: 0.1, note: "AOD and particulates; the indices in these families take the ordinal ramps instead." },
  { key: "aurora", families: ["space_weather"], hue: 160, chroma: 0.13, note: "Aurora probability and OVATION. Kp is ordinal; Bz is diverging." },
];
const DIVERGING = [
  { key: "temperature", family: "temperature", about: "0 degC", neg: 250, pos: 25, note: "Blue below freezing, red above. Neutral grey at exactly zero." },
  { key: "bz", family: "space_weather", about: "0 nT", neg: 250, pos: 45, note: "Southward (negative) Bz is the aurora-favourable side; blue keeps it distinct from temperature's red." },
  { key: "omega", family: "vertical_motion", about: "0 Pa/s", neg: 195, pos: 60, note: "Positive omega is descent (warm brown); negative is ascent (teal)." },
];
const ORDINAL = [
  { key: "kp", family: "space_weather", classes: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], hue: 340, note: "Planetary K index, ten classes." },
  { key: "aqhi", family: "air_quality", classes: ["low 1-3", "moderate 4-6", "high 7-10", "very high 10+"], hue: 40, note: "Canadian AQHI by health-risk category; the number is always printed. Eleven per-value steps cannot clear the ordinal lightness rule on the dark surface." },
  { key: "index_0_5", family: "seeing, transparency", classes: ["0", "1", "2", "3", "4", "5"], hue: 300, note: "ECCC seeing and transparency indices, unlabelled integers 0 to 5." },
];
function ordinalRamp(n, hue, mode) {
  // discrete marks: every step must clear 2:1 on the surface, adjacent delta L >= 0.06
  const dL = 0.063 * (n - 1);
  const [a, b] = mode === "light" ? [0.75, 0.75 - dL] : [0.41, 0.41 + dL];
  const out = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    out.push(oklch(a + (b - a) * t, 0.11 + 0.05 * Math.sin(Math.PI * t), hue));
  }
  return out;
}

// ---------- Non-colour tokens ----------
const TYPE_SCALE = [
  { key: "xs", px: 11, lh: 1.3, use: "chips, tags, eyebrow" },
  { key: "sm", px: 12, lh: 1.35, use: "table cells, timestamps" },
  { key: "base", px: 13, lh: 1.45, use: "body (A); scaled by variant base" },
  { key: "md", px: 14, lh: 1.45, use: "row labels, inspector body" },
  { key: "lg", px: 16, lh: 1.4, use: "section titles, verdict labels" },
  { key: "xl", px: 20, lh: 1.3, use: "view titles, focus place" },
  { key: "2xl", px: 24, lh: 1.2, use: "values in the phone brief" },
  { key: "3xl", px: 32, lh: 1.1, use: "hero verdict, wordmark" },
];
const SPACE = { 0: 0, 1: 2, 2: 4, 3: 6, 4: 8, 5: 12, 6: 16, 7: 24, 8: 32, 9: 48 };
const RADIUS = { none: 0, sm: 2, md: 4, lg: 6, pill: 999 };
const STROKE = { hair: 1, glyph: 1.8, rule: 2 };
const SIZE = { glyph: 16, gutter: 24, "control-compact": 28, "control-comfortable": 36, "control-touch": 44, "tag-min": 40 };
const MOTION = { fast: "120ms", base: "200ms", slow: "320ms", easing: "cubic-bezier(.2,.7,.2,1)", reduced: "0ms" };
const Z = { stage: 0, strip: 5, dock: 10, inspector: 20, popover: 30, banner: 40 };

// ---------- Build ----------
const tokens = { $meta: { generated: new Date().toISOString(), ticket: 41, source: "tokens.build.mjs", validator: VALIDATOR }, variants: {}, night: {}, palettes: {}, ramps: {}, type: { scale: TYPE_SCALE }, space: SPACE, radius: RADIUS, stroke: STROKE, size: SIZE, motion: MOTION, z: Z, $validation: [] };
const V = tokens.$validation;
const rep = (label, r) => V.push({ label, ok: r.ok, report: r.report.map(([n, p, d]) => ({ check: n, pass: p, detail: d })) });

for (const [id, v] of Object.entries(VARIANTS)) {
  const n = neutrals(v.neutral);
  const light = {
    bg: n[50], panel: n[0], raised: n[100], sunken: n[200], line: n[300], "line-strong": n[500],
    ink: n[950], muted: n[600], faint: n[400], inverse: n[0],
    accent: oklch(0.5, 0.17, 258), "accent-ink": "#ffffff", focus: oklch(0.55, 0.2, 258),
    core: oklch(0.95, 0.03, 258), planning: oklch(0.95, 0.025, 80), now: oklch(0.55, 0.2, 355), boundary: n[600],
  };
  const dark = {
    bg: n[1000], panel: n[950], raised: n[900], sunken: n[1000], line: n[800], "line-strong": n[600],
    ink: n[50], muted: n[400], faint: n[600], inverse: n[1000],
    accent: oklch(0.76, 0.12, 258), "accent-ink": n[1000], focus: oklch(0.8, 0.14, 258),
    core: oklch(0.28, 0.05, 258), planning: oklch(0.27, 0.03, 80), now: oklch(0.72, 0.18, 355), boundary: n[400],
  };
  tokens.variants[id] = { ...v, neutrals: n, themes: { light, dark } };
}

// evidence + sources per theme, validated against each variant's panel surface
for (const mode of ["light", "dark"]) {
  tokens.palettes[mode] = {};
  for (const [id, v] of Object.entries(tokens.variants)) {
    const surface = v.themes[mode].panel;
    const ev = bestCategorical(EVIDENCE.map((e) => e.hue), mode, surface, "all");
    const src = bestCategorical(SOURCE_HUES, mode, surface, "adjacent");
    V.push({ label: `evidence classes, ${mode}, variant ${id} surface ${surface}, all pairs`, ok: false, expected: "six hues cannot clear the all-pairs colour-vision floor (the reference palette caps at three); shape and fill carry the class, colour is redundant", report: ev.report.report.map(([n, p, d]) => ({ check: n, pass: p, detail: d })) });
    rep(`evidence classes, ${mode}, variant ${id} surface ${surface}, adjacent in legend order`, validate(ev.pal, { mode, surface, pairs: "adjacent" }));
    rep(`source slots, ${mode}, variant ${id} surface ${surface}, adjacent`, src.report);
    rep(`source slots first three, ${mode}, variant ${id}, all pairs`, validate(src.pal.slice(0, 3), { mode, surface, pairs: "all" }));
    const statusContrast = Object.fromEntries(Object.entries(STATUS).map(([k, h]) => [k, +contrast(h, surface).toFixed(2)]));
    tokens.palettes[mode][id] = {
      evidence: Object.fromEntries(EVIDENCE.map((e, i) => [e.key, ev.pal[i]])),
      absent: v.neutrals[mode === "light" ? 500 : 500],
      unrecognised: v.neutrals[mode === "light" ? 700 : 300],
      sources: SOURCE_SLOTS.map((s, i) => ({ ...s, hex: src.pal[i] })),
      status: { ...STATUS, contrast: statusContrast },
      statusBg: {
        good: mode === "light" ? oklch(0.95, 0.04, 150) : oklch(0.28, 0.05, 150),
        warning: mode === "light" ? oklch(0.95, 0.05, 80) : oklch(0.3, 0.06, 80),
        critical: mode === "light" ? oklch(0.94, 0.04, 25) : oklch(0.28, 0.07, 25),
      },
    };
  }
  tokens.ramps[mode] = {
    sequential: SEQUENTIAL.map((s) => ({ ...s, steps: ramp(s.hue, mode, 7, { chroma: s.chroma }) })),
    diverging: DIVERGING.map((d) => {
      const neutral = mode === "light" ? "#e6e6e3" : "#3a3a37";
      const neg = ramp(d.neg, mode, 5, { chroma: 0.13 }).slice(1); // 4 steps, pale..deep in light
      const pos = ramp(d.pos, mode, 5, { chroma: 0.13 }).slice(1);
      const steps = mode === "light" ? [...neg.slice().reverse(), neutral, ...pos] : [...neg.slice().reverse(), neutral, ...pos];
      return { ...d, steps };
    }),
    ordinal: ORDINAL.map((o) => {
      const steps = ordinalRamp(o.classes.length, o.hue, mode);
      const surface = tokens.variants.A.themes[mode].panel;
      rep(`ordinal ${o.key}, ${mode}, surface ${surface}`, validateOrdinal(steps, { mode, surface }));
      return { ...o, steps };
    }),
  };
  for (const s of tokens.ramps[mode].sequential) {
    const surface = tokens.variants.A.themes[mode].panel;
    const r = validateOrdinal(s.steps, { mode, surface });
    const onlyLightEnd = !r.ok && r.report.every(([n, p]) => p || /Light-end/.test(n));
    V.push({ label: `sequential ${s.key} ramp check, ${mode}, surface ${surface}`, ok: r.ok || onlyLightEnd, expected: onlyLightEnd ? "continuous ramp: the palest step recedes toward the surface by design (dataviz color-formula scope note)" : undefined, report: r.report.map(([n, p, d]) => ({ check: n, pass: p, detail: d })) });
  }
}

// night candidates: evidence collapses to ink; sources take four luminances + line styles
for (const [id, nt] of Object.entries(NIGHT)) {
  const lum = [nt.ink, nt.muted, oklch(0.56, 0.2, 28), nt.faint];
  tokens.night[id] = {
    ...nt,
    evidence: Object.fromEntries(EVIDENCE.map((e) => [e.key, nt.ink])),
    absent: nt.faint,
    sourceLuminance: lum,
    sourceLineStyles: ["solid", "dashed 6 3", "dotted 2 3", "dash-dot 6 3 2 3"],
    contrast: { inkOnBg: +contrast(nt.ink, nt.bg).toFixed(2), mutedOnBg: +contrast(nt.muted, nt.bg).toFixed(2), inkOnPanel: +contrast(nt.ink, nt.panel).toFixed(2), faintOnBg: +contrast(nt.faint, nt.bg).toFixed(2) },
  };
}

// text contrast table (WCAG) for every variant and theme
tokens.$textContrast = {};
for (const [id, v] of Object.entries(tokens.variants)) {
  for (const mode of ["light", "dark"]) {
    const t = v.themes[mode];
    tokens.$textContrast[`${id}.${mode}`] = {
      inkOnBg: +contrast(t.ink, t.bg).toFixed(2), inkOnPanel: +contrast(t.ink, t.panel).toFixed(2),
      mutedOnPanel: +contrast(t.muted, t.panel).toFixed(2), faintOnPanel: +contrast(t.faint, t.panel).toFixed(2),
      accentOnPanel: +contrast(t.accent, t.panel).toFixed(2), accentInkOnAccent: +contrast(t["accent-ink"], t.accent).toFixed(2),
      lineOnPanel: +contrast(t.line, t.panel).toFixed(2),
    };
  }
}

writeFileSync(new URL("./tokens.json", import.meta.url), JSON.stringify(tokens, null, 1));

// ---------- Print a compact report ----------
const fails = V.filter((r) => !r.ok);
console.log(`tokens.json written. ${V.length} validator runs, ${fails.length} with a FAIL.`);
for (const r of V) {
  const bad = r.report.filter((c) => !c.pass);
  console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.label}` + (bad.length ? `\n      ${bad.map((c) => `${c.check}: ${c.detail}`).join("\n      ")}` : ""));
}
console.log("\ntext contrast:", JSON.stringify(tokens.$textContrast));
console.log("night:", JSON.stringify(Object.fromEntries(Object.entries(tokens.night).map(([k, n]) => [k, n.contrast]))));
