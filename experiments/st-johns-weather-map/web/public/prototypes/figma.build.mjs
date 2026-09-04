// PROTOTYPE, throwaway. Emits Figma Plugin API scripts (one per step) from
// tokens.json so the variable library can be written with use_figma.
// The Figma starter plan allows ONE mode per collection, so every mode is its
// own collection ("Theme · Light", "Theme · Dark", ...). Each script is
// self-contained and idempotent: collections and variables are looked up by
// name before being created.
//
//   node figma.build.mjs [out-dir]   (default ./figma-scripts)
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
const OUT = process.argv[2] ?? "./figma-scripts";
mkdirSync(OUT, { recursive: true });
const T = JSON.parse(readFileSync(new URL("./tokens.json", import.meta.url), "utf8"));
const NIGHT = process.env.NIGHT ?? "red";
const LEAD = process.env.LEAD ?? "A";

const RUNNER = `
const hex = (h) => { h = h.replace('#',''); return { r: parseInt(h.slice(0,2),16)/255, g: parseInt(h.slice(2,4),16)/255, b: parseInt(h.slice(4,6),16)/255 }; };
const all = await figma.variables.getLocalVariablesAsync();
const cols = await figma.variables.getLocalVariableCollectionsAsync();
for (const c of cols) if (c.name === 'Variant' && c.variableIds.length === 0) c.remove();
function collection(name) {
  let c = cols.find((x) => x.name === name);
  if (!c) { c = figma.variables.createVariableCollection(name); c.renameMode(c.modes[0].modeId, 'Value'); cols.push(c); }
  return c;
}
function find(colName, varName) {
  const c = cols.find((x) => x.name === colName);
  return c && all.find((x) => x.name === varName && x.variableCollectionId === c.id);
}
let created = 0, updated = 0;
for (const s of SPEC) {
  const c = collection(s.collection);
  let v = all.find((x) => x.name === s.name && x.variableCollectionId === c.id);
  if (!v) { v = figma.variables.createVariable(s.name, c, s.type); all.push(v); created++; } else updated++;
  v.scopes = s.scopes;
  if (s.css) v.setVariableCodeSyntax('WEB', s.css);
  if (s.description) v.description = s.description;
  let value = s.value;
  if (value && value.hex) value = hex(value.hex);
  else if (value && value.alias) { const t = find(value.alias[0], value.alias[1]); if (!t) throw new Error('missing alias target ' + value.alias.join('/')); value = { type: 'VARIABLE_ALIAS', id: t.id }; }
  v.setValueForMode(c.modes[0].modeId, value);
}
return { created, updated, collections: cols.map((c) => c.name + ' (' + c.variableIds.length + ')') };
`;
const emit = (file, spec) => { writeFileSync(`${OUT}/${file}`, `const SPEC = ${JSON.stringify(spec)};\n${RUNNER}`); return spec.length; };
const sizes = {};

// ---- 1. Variant collections: neutrals, fonts, base, control ----
{
  const spec = [];
  for (const v of Object.values(T.variants)) {
    const col = `Variant · ${v.name}`;
    for (const [k, h] of Object.entries(v.neutrals)) spec.push({ collection: col, name: `neutral/${k}`, type: "COLOR", scopes: [], css: `var(--n-${k})`, value: { hex: h } });
    for (const f of ["ui", "display", "mono"]) spec.push({ collection: col, name: `font/${f}`, type: "STRING", scopes: ["FONT_FAMILY"], css: `var(--font-${f})`, value: v.fonts[f].split(",")[0].replace(/"/g, "") });
    spec.push({ collection: col, name: "type/base", type: "FLOAT", scopes: ["FONT_SIZE"], css: "var(--fs-base)", value: v.base });
    spec.push({ collection: col, name: "size/control", type: "FLOAT", scopes: ["WIDTH_HEIGHT"], css: "var(--control)", value: T.size[`control-${v.density === "compact" ? "compact" : v.density === "comfortable" ? "comfortable" : "touch"}`] });
  }
  sizes["01-variant.js"] = emit("01-variant.js", spec);
}

// ---- 2. Theme collections (Light, Dark alias the lead variant's neutrals; Night literal) ----
{
  const A = T.variants[LEAD];
  const stepOf = Object.fromEntries(Object.entries(A.neutrals).map(([k, h]) => [h, k]));
  const leadCol = `Variant · ${A.name}`;
  const spec = [];
  const surfaceKeys = ["bg", "panel", "raised", "sunken", "line", "line-strong", "ink", "muted", "faint", "inverse"];
  const scopeFor = (k) => (/ink|muted|faint|inverse/.test(k) ? ["TEXT_FILL", "SHAPE_FILL", "STROKE_COLOR"] : /line/.test(k) ? ["STROKE_COLOR"] : ["FRAME_FILL", "SHAPE_FILL"]);
  const n = T.night[NIGHT];
  const nightMap = { bg: n.bg, panel: n.panel, raised: n.raised, sunken: n.bg, line: n.line, "line-strong": n.muted, ink: n.ink, muted: n.muted, faint: n.faint, inverse: n.bg };
  for (const mode of ["Light", "Dark"]) {
    const t = A.themes[mode.toLowerCase()];
    for (const k of surfaceKeys) {
      const group = /ink|muted|faint|inverse/.test(k) ? "ink" : "surface";
      const st = stepOf[t[k]];
      spec.push({ collection: `Theme · ${mode}`, name: `${group}/${k}`, type: "COLOR", scopes: scopeFor(k), css: `var(--${k})`, value: st ? { alias: [leadCol, `neutral/${st}`] } : { hex: t[k] } });
    }
  }
  for (const k of surfaceKeys) spec.push({ collection: "Theme · Night", name: `${/ink|muted|faint|inverse/.test(k) ? "ink" : "surface"}/${k}`, type: "COLOR", scopes: scopeFor(k), css: `var(--${k})`, value: { hex: nightMap[k] } });
  const lit = (name, l, d, nt, scopes, css, description) => {
    spec.push({ collection: "Theme · Light", name, type: "COLOR", scopes, css, value: { hex: l }, description });
    spec.push({ collection: "Theme · Dark", name, type: "COLOR", scopes, css, value: { hex: d }, description });
    spec.push({ collection: "Theme · Night", name, type: "COLOR", scopes, css, value: { hex: nt }, description });
  };
  const L = A.themes.light, D = A.themes.dark, PL = T.palettes.light[LEAD], PD = T.palettes.dark[LEAD];
  lit("accent/accent", L.accent, D.accent, n.accent, ["FRAME_FILL", "SHAPE_FILL", "TEXT_FILL", "STROKE_COLOR"], "var(--accent)");
  lit("accent/on-accent", L["accent-ink"], D["accent-ink"], n.bg, ["TEXT_FILL"], "var(--accent-ink)");
  lit("accent/focus", L.focus, D.focus, n.accent, ["STROKE_COLOR"], "var(--focus)");
  lit("rail/core", L.core, D.core, n.raised, ["FRAME_FILL", "SHAPE_FILL"], "var(--core)");
  lit("rail/planning", L.planning, D.planning, n.panel, ["FRAME_FILL", "SHAPE_FILL"], "var(--planning)");
  lit("rail/now", L.now, D.now, n.accent, ["SHAPE_FILL", "STROKE_COLOR"], "var(--now)");
  lit("rail/boundary", L.boundary, D.boundary, n.muted, ["STROKE_COLOR"], "var(--boundary)");
  lit("status/good", PL.status.good, PD.status.good, n.ink, ["SHAPE_FILL", "TEXT_FILL", "STROKE_COLOR"], "var(--good)", "dataviz fixed status scale; never without glyph and word");
  lit("status/warning", "#8a5a00", PD.status.warning, n.warn, ["SHAPE_FILL", "TEXT_FILL", "STROKE_COLOR"], "var(--warn)", "light uses a text-safe amber; the dataviz #fab219 is 1.8:1 on white");
  lit("status/serious", PL.status.serious, PD.status.serious, n.warn, ["SHAPE_FILL", "TEXT_FILL", "STROKE_COLOR"], "var(--serious)");
  lit("status/critical", PL.status.critical, PD.status.critical, n.bad, ["SHAPE_FILL", "TEXT_FILL", "STROKE_COLOR"], "var(--bad)");
  lit("status/good-bg", PL.statusBg.good, PD.statusBg.good, n.panel, ["FRAME_FILL", "SHAPE_FILL"], "var(--good-bg)");
  lit("status/warning-bg", PL.statusBg.warning, PD.statusBg.warning, n.raised, ["FRAME_FILL", "SHAPE_FILL"], "var(--warn-bg)");
  lit("status/critical-bg", PL.statusBg.critical, PD.statusBg.critical, n.raised, ["FRAME_FILL", "SHAPE_FILL"], "var(--bad-bg)");
  for (const k of Object.keys(PL.evidence)) lit(`class/${k}`, PL.evidence[k], PD.evidence[k], n.ink, ["SHAPE_FILL", "STROKE_COLOR", "TEXT_FILL"], `var(--cls-${k})`, "evidence class colour; redundant to the glyph shape and fill");
  lit("class/absent", PL.absent, PD.absent, n.faint, ["SHAPE_FILL", "STROKE_COLOR", "TEXT_FILL"], "var(--absent)");
  lit("class/unrecognised", PL.unrecognised, PD.unrecognised, n.muted, ["SHAPE_FILL", "STROKE_COLOR", "TEXT_FILL"], "var(--unrecognised)");
  PL.sources.forEach((src, i) => lit(`source/${src.slot}-${src.hue}`, src.hex, PD.sources[i].hex, n.sourceLuminance[i % 4], ["SHAPE_FILL", "STROKE_COLOR"], `var(--src-${src.slot})`, `${src.provider}: ${src.sources.join(", ")}`));
  sizes["02-theme.js"] = emit("02-theme.js", spec);
}

// ---- 3. Dimension: space, radius, stroke, size, type scale, motion ----
{
  const spec = [];
  const num = (name, val, scopes, css) => spec.push({ collection: "Dimension", name, type: "FLOAT", scopes, css, value: val });
  for (const [k, px] of Object.entries(T.space)) num(`space/${k}`, px, ["GAP", "WIDTH_HEIGHT"], `var(--sp-${k})`);
  for (const [k, px] of Object.entries(T.radius)) num(`radius/${k}`, px, ["CORNER_RADIUS"], `var(--r-${k})`);
  for (const [k, px] of Object.entries(T.stroke)) num(`stroke/${k}`, px, ["STROKE_FLOAT"], `var(--stroke-${k})`);
  for (const [k, px] of Object.entries(T.size)) num(`size/${k}`, px, ["WIDTH_HEIGHT"], `var(--size-${k})`);
  for (const t of T.type.scale) { num(`type/${t.key}/size`, t.px, ["FONT_SIZE"], `var(--fs-${t.key})`); num(`type/${t.key}/line-height`, Math.round(t.px * t.lh), ["LINE_HEIGHT"], `var(--lh-${t.key})`); }
  for (const [k, v] of Object.entries(T.motion)) spec.push({ collection: "Dimension", name: `motion/${k}`, type: "STRING", scopes: [], css: `var(--motion-${k})`, value: v });
  sizes["03-dimension.js"] = emit("03-dimension.js", spec);
}

// ---- 4. Ramps · Light / Ramps · Dark, compact: one entry per ramp ----
{
  const R = [];
  for (const mode of ["light", "dark"]) for (const kind of ["sequential", "diverging", "ordinal"]) for (const r of T.ramps[mode][kind]) R.push({ c: `Ramps · ${mode[0].toUpperCase()}${mode.slice(1)}`, k: `${kind}/${r.key}`, n: r.note, s: r.steps });
  const RUNNER2 = RUNNER.replace("for (const s of SPEC) {", "const SPEC = []; for (const r of R) r.s.forEach((hx, i) => SPEC.push({ collection: r.c, name: r.k + '/' + (i + 1), type: 'COLOR', scopes: ['SHAPE_FILL', 'FRAME_FILL'], css: 'var(--' + r.k.replace('/', '-') + '-' + (i + 1) + ')', value: { hex: hx }, description: r.n }));\nfor (const s of SPEC) {");
  writeFileSync(`${OUT}/04-ramps.js`, `const R = ${JSON.stringify(R)};\n${RUNNER2}`);
  sizes["04-ramps.js"] = R.reduce((a, r) => a + r.s.length, 0);
}
console.log(Object.entries(sizes).map(([n, c]) => `${n}: ${c} variables`).join("\n"));
