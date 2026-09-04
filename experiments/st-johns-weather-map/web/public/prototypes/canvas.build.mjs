// PROTOTYPE, throwaway. Writes the Claude Design artboards for ticket #41 from
// tokens.json: the one sample screen in light, dark and night for the leading
// variant, plus the two alternative variants in light, plus a token sheet.
// Colours are resolved to literal hex so each artboard stands alone.
//
//   node canvas.build.mjs [out-dir]   (default ./canvas)
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

const OUT = process.argv[2] ?? "./canvas";
mkdirSync(OUT, { recursive: true });
const T = JSON.parse(readFileSync(new URL("./tokens.json", import.meta.url), "utf8"));
const page = readFileSync(new URL("./tokens.html", import.meta.url), "utf8");
const appCss = page.slice(page.indexOf("/* ---------- the themed sample"), page.indexOf("/* ---------- token sheets"));
const symbols = page.slice(page.indexOf("<symbol"), page.lastIndexOf("</symbol>") + 9);
const LEAD = process.env.LEAD ?? "A", NIGHT = process.env.NIGHT ?? "red";

// live values if the proxy is up, else the captured GFS values
let temp = 10.86, wind = 2.61, cloud = 0, instant = "2026-09-03T22:00:00Z", note = "captured GFS values";
try {
  const tl = await (await fetch("http://localhost:5199/api/experiments/weather/v0/timeline")).json();
  const first = (tl.items ?? []).find((i) => (i.available_products ?? []).length);
  if (first) instant = first.valid_time_utc;
  const p = await (await fetch(`http://localhost:5199/api/experiments/weather/v0/point?latitude=47.5615&longitude=-52.7126&valid_time=${instant}`)).json();
  const f = Object.fromEntries(p.fields.map((x) => [x.field, x]));
  temp = f.temperature?.value ?? temp; wind = f.wind_speed?.value ?? wind; cloud = f.total_cloud_geometric?.value ?? cloud;
  note = `live GFS values at ${instant}`;
} catch {}

function vars(vId, theme) {
  const v = T.variants[vId], o = {};
  o["--font-ui"] = v.fonts.ui; o["--font-display"] = v.fonts.display; o["--font-mono"] = v.fonts.mono;
  const scale = v.base / 13;
  for (const s of T.type.scale) o[`--fs-${s.key}`] = `${Math.round(s.px * scale * 10) / 10}px`;
  for (const [k, px] of Object.entries(T.space)) o[`--sp-${k}`] = `${px}px`;
  for (const [k, px] of Object.entries(T.radius)) o[`--r-${k}`] = `${px}px`;
  o["--glyph"] = `${T.size.glyph}px`; o["--gutter"] = `${T.size.gutter}px`;
  o["--control"] = `${T.size[`control-${v.density === "compact" ? "compact" : v.density === "comfortable" ? "comfortable" : "touch"}`]}px`;
  o["--tabs-w"] = v.density === "spacious" ? "64px" : "52px";
  if (theme === "night") {
    const n = T.night[NIGHT];
    Object.assign(o, { "--bg": n.bg, "--panel": n.panel, "--raised": n.raised, "--sunken": n.bg, "--line": n.line, "--ink": n.ink, "--muted": n.muted, "--faint": n.faint, "--absent": n.faint, "--accent": n.accent, "--accent-ink": n.bg, "--focus": n.accent, "--good": n.ink, "--warn": n.warn, "--bad": n.bad, "--good-bg": n.panel, "--warn-bg": n.raised, "--bad-bg": n.raised, "--core": n.raised, "--planning": n.panel, "--now": n.accent, "--boundary": n.muted });
    for (const [k, hex] of Object.entries(n.evidence)) o[`--cls-${k}`] = hex;
    [n.bg, n.panel, n.panel, n.raised, n.raised, n.line, n.line].forEach((h, i) => (o[`--ramp-cloud-${i + 1}`] = h));
    n.sourceLuminance.forEach((hex, i) => (o[`--src-${i + 1}`] = hex));
    return o;
  }
  const t = v.themes[theme], P = T.palettes[theme][vId];
  for (const [k, hex] of Object.entries(t)) o[`--${k}`] = hex;
  o["--good"] = P.status.good; o["--warn"] = theme === "light" ? "#8a5a00" : P.status.warning; o["--bad"] = P.status.critical;
  o["--good-bg"] = P.statusBg.good; o["--warn-bg"] = P.statusBg.warning; o["--bad-bg"] = P.statusBg.critical;
  for (const [k, hex] of Object.entries(P.evidence)) o[`--cls-${k}`] = hex;
  o["--absent"] = P.absent;
  P.sources.forEach((s) => (o[`--src-${s.slot}`] = s.hex));
  T.ramps[theme].sequential.find((r) => r.key === "cloud").steps.forEach((hex, i) => (o[`--ramp-cloud-${i + 1}`] = hex));
  return o;
}
// The canvas renderer drops inline SVG, so the glyphs are drawn with CSS here; the HTML prototype keeps the SVG symbol set.
const GLYPH_CSS = `
  .cg { display: inline-block; width: 16px; height: 16px; position: relative; vertical-align: middle; flex: 0 0 16px; }
  .cg::before { content: ""; position: absolute; inset: 2px; box-sizing: border-box; }
  .cg-retrieved::before { border-radius: 50%; background: currentColor; }
  .cg-reprocessed::before { border-radius: 50%; border: 1.8px solid currentColor; background: linear-gradient(90deg, transparent 50%, currentColor 50%); }
  .cg-derived_here::before { inset: 3px; transform: rotate(45deg); background: currentColor; }
  .cg-intermediary_derived::before { inset: 3.5px; transform: rotate(45deg); border: 1.8px solid currentColor; }
  .cg-generated_display::before { border-radius: 50%; border: 1.8px dashed currentColor; }
  .cg-uncalibrated_observation::before { inset: 1.5px 1px 2px; background: currentColor; clip-path: polygon(50% 0, 100% 100%, 0 100%); }
  .cg-uncalibrated_observation::after { content: ""; position: absolute; inset: 5.5px 4.2px 3.9px; background: var(--panel); clip-path: polygon(50% 0, 100% 100%, 0 100%); }
  .cg-unrecognised::before { inset: 2.5px; border: 1.8px solid currentColor; }
  .cg-unrecognised::after { content: "?"; position: absolute; inset: 0; font: 700 9px/16px var(--font-mono); text-align: center; }
  .cg-absent::before { inset: 7px 3px; background: currentColor; }
`;
const glyph = (cls) => `<span class="cg cg-${cls} g-${cls}" role="img" aria-label="${cls.replace(/_/g, " ")}"></span>`;
const rows = [
  { cls: "retrieved", src: "GFS", label: "Air temperature 2 m", val: temp.toFixed(1), unit: "°C" },
  { cls: "derived_here", src: "GFS", label: "Wind speed 10 m", val: wind.toFixed(2), unit: "m/s" },
  { cls: "retrieved", src: "GFS", label: "Total cloud, geometric", val: cloud.toFixed(0), unit: "%" },
  { cls: "retrieved", src: "HRDPS", label: "Total cloud, opacity-weighted", val: "38", unit: "%", chip: `<span class="chip warn">run stale</span>`, sel: true, c: true },
  { cls: "reprocessed", src: "UKMO·OM", label: "Dew point 2 m", val: "9.4", unit: "°C", c: true },
  { cls: "intermediary_derived", src: "7TIMER", label: "Seeing index", val: "3", unit: "", c: true },
  { cls: "generated_display", src: "HRDPS", label: "Low cloud, between frames", val: "41", unit: "%", c: true },
  { cls: "uncalibrated_observation", src: "CWOP", label: "Pressure, station", val: "1011.2", unit: "hPa", c: true },
  { cls: "absent", src: "CYYT TAF", label: "Visibility", val: null, unit: "", chip: `<span class="chip">null · provenance_unmodelled</span>` },
  { cls: "absent", src: "WN2", label: "Temperature 2 m", val: "blocked", unit: "", chip: `<span class="chip bad">blocked</span>`, c: true },
  { cls: "absent", src: "GOES", label: "Cloud-top height", val: "aged out", unit: "", chip: `<span class="chip warn">held to 18:10Z</span>`, c: true },
];
const ledger = rows.map((r) => `<div class="lrow" role="row" tabindex="0"${r.sel ? ' aria-selected="true"' : ""}>${glyph(r.cls)}<span class="tag-src">${r.src}</span><span class="label">${r.label}${r.c ? ' <span class="chip" style="font-size: 9px; padding: 0 4px;">constructed</span>' : ""}</span><span class="val${r.val == null || /blocked|aged/.test(r.val) ? " absent" : ""}">${r.val ?? "—"}<span class="u">${r.unit}</span></span><span>${r.chip ?? ""}</span></div>`).join("\n");
const SERIES = [
  { tag: "HRDPS", slot: 1, dash: "", pts: [12.9, 13.1, 13.4, 13.2, 12.6, 12.1, 11.4, 10.9] },
  { tag: "RDPS", slot: 1, dash: "6 3", pts: [12.4, 12.8, 13.0, 12.7, 12.2, 11.6, 11.0, 10.4] },
  { tag: "GFS", slot: 2, dash: "", pts: [13.4, 13.6, 13.7, 13.3, 12.7, 12.0, 11.3, 10.8] },
  { tag: "IFS", slot: 3, dash: "", pts: [12.6, 12.9, 13.2, 13.0, 12.5, 11.9, 11.2, 10.6] },
  { tag: "ICON", slot: 4, dash: "", pts: [12.1, 12.5, 12.9, 12.8, 12.3, 11.7, 11.1, 10.5] },
];
const NIGHT_DASH = ["", "6 3", "2 3", "6 3 2 3"];
function chart(theme) {
  const W = 420, H = 100, x = (i) => 8 + (i * (W - 16)) / 7, y = (v) => H - 8 - ((v - 10) / 4.2) * (H - 16);
  const lines = SERIES.map((s, i) => `<polyline fill="none" stroke="var(--src-${theme === "night" ? (i % 4) + 1 : s.slot})" stroke-width="2" stroke-dasharray="${theme === "night" ? NIGHT_DASH[i % 4] : s.dash}" stroke-linejoin="round" points="${s.pts.map((v, j) => `${x(j)},${y(v)}`).join(" ")}"></polyline>`).join("");
  const grid = [10, 12, 14].map((v) => `<line x1="0" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-width="1"></line><text x="2" y="${y(v) - 2}" font-size="8" fill="var(--faint)">${v}°</text>`).join("");
  const leg = SERIES.map((s, i) => `<span><svg viewBox="0 0 22 10"><line x1="1" x2="21" y1="5" y2="5" stroke="var(--src-${theme === "night" ? (i % 4) + 1 : s.slot})" stroke-width="2" stroke-dasharray="${theme === "night" ? NIGHT_DASH[i % 4] : s.dash}"></line></svg>${s.tag}</span>`).join("");
  const css = { "": "solid", "6 3": "dashed", "2 3": "dotted", "6 3 2 3": "dashed" };
  const legCss = SERIES.map((s, i) => `<span style="display: inline-flex; align-items: center; gap: 4px;"><i style="display: inline-block; width: 22px; border-top: 2px ${css[theme === "night" ? NIGHT_DASH[i % 4] : s.dash]} var(--src-${theme === "night" ? (i % 4) + 1 : s.slot});"></i>${s.tag}</span>`).join("");
  return `<div style="height: 70px; display: flex; align-items: flex-end; gap: 6px; padding: 6px 0;">${SERIES.map((s, i) => `<div style="flex: 1 1 0; height: ${20 + i * 9}px; border-top: 2px ${css[theme === "night" ? NIGHT_DASH[i % 4] : s.dash]} var(--src-${theme === "night" ? (i % 4) + 1 : s.slot}); opacity: .9;"></div>`).join("")}</div><div class="leg" style="display: flex; gap: 12px; font-size: var(--fs-xs); color: var(--muted);">${legCss}<span style="margin-left: auto; color: var(--faint);">line chart lives in tokens.html (SVG)</span></div>`;
}
const stackRow = (cls, name, tag) => `<div class="row">${glyph(cls)}<span>${name}</span><span class="tag-src" style="font-size: var(--fs-xs); color: var(--muted);">${tag}</span></div>`;
function screen(vId, theme, title) {
  const o = vars(vId, theme);
  const local = new Date(instant).toLocaleString("en-CA", { timeZone: "America/St_Johns", weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?${T.variants[vId].fonts.google}&display=swap">
  <style>
    body { margin: 0; background: ${o["--bg"]}; }
    a { color: ${o["--accent"]}; } a:hover { color: ${o["--ink"]}; }
    .root { width: 1440px; min-height: 900px; ${Object.entries(o).map(([k, v]) => `${k}: ${v};`).join(" ")} }
    ${appCss}
    ${GLYPH_CSS}
    .app { min-height: 900px; }
    .caption { position: absolute; left: 0; right: 0; top: -22px; font: 11px system-ui, sans-serif; color: #888; }
  </style>
</helmet>
<div class="root" style="position: relative;">
  <div class="app" data-theme="${theme}" style="color-scheme: ${theme === "light" ? "light" : "dark"};">
    <div class="focusbar">
      <div><div class="place">Signal Hill <span class="sub">· 1.9 km NE of CYYT</span></div><div class="sub"><span class="time">${local} NDT · ${instant.slice(11, 16)}Z</span> · horizon: not borrowed</div></div>
      <span class="chip tier">core · 15 min</span>
      <span class="chip good">${glyph("retrieved")} live</span>
    </div>
    <div class="datamode"><span><b>live</b> mode</span><span><b>1</b> source with values</span><span><b>0</b> stale</span><span><b>0</b> aged out</span><span><b>1</b> notice</span><span style="margin-left: auto;">details</span></div>
    <div class="stage">
      <div class="tabs" role="tablist"><button role="tab" aria-selected="true">Map</button><button role="tab" aria-selected="false">Series</button><button role="tab" aria-selected="false">Sky</button><button role="tab" aria-selected="false">Activity</button><button role="tab" aria-selected="false">Sources</button></div>
      <div class="map"><div class="fake"></div>
        <div class="stack">${stackRow("retrieved", "GOES natural colour", "GOES")}${stackRow("generated_display", "Total cloud, opacity", "HRDPS")}${stackRow("retrieved", "Alerts in force", "MSC")}${stackRow("retrieved", "Radar composite", "ECCC")}</div>
        <div class="corner"><div class="row">${glyph("retrieved")}<span>GOES</span><span class="time">20:50Z</span><span>10 min</span></div><div class="row">${glyph("generated_display")}<span>HRDPS</span><span class="time">${instant.slice(11, 16)}Z</span><span>between</span></div><div class="row">${glyph("retrieved")}<span>MSC</span><span>current</span></div><div class="row">${glyph("absent")}<span>ECCC radar</span><span>not drawn</span></div></div>
        <div class="strip">${glyph("generated_display")}<span class="gen">GENERATED</span><span>Total cloud between frames</span><span>·</span><span><b>3 of 4</b> drawn at ${instant.slice(11, 16)}Z</span><span class="exc">· radar: newest scan 2.4 h old, beyond tolerance</span><span class="why">why?</span></div>
      </div>
      <div class="dock">
        <h3>Series <small>at the Focus · 54 fields</small></h3>
        <div class="ledger" role="grid">${ledger}</div>
        <div class="series">${chart(theme)}</div>
        <div class="lane"><div><div class="name">Astronomy</div><div class="limit">limited by cloud, opacity-weighted</div></div><div class="vstrip">${"gggggwwwbbnnpppp".split("").map((c) => `<i class="${c === "g" ? "" : c}"></i>`).join("")}</div><div class="verdict"><i class="mark"></i><b>Go · 78</b><span class="chip">coverage 0.81</span></div></div>
      </div>
    </div>
    <div class="rail"><button class="primary">▶</button><div class="track"><i class="now"></i><i class="tier"></i></div><span class="time">−15 d ··· <b>now</b> ··· +15 d</span></div>
  </div>
</div>
</x-dc>
</body>
</html>
`;
}

// token sheet artboard: swatches with hex, for the leading variant, both modes + night
function sheet() {
  const cells = (title, entries, bg, ink) => `<div style="display: flex; flex-direction: column; gap: 8px; padding: 16px; background: ${bg}; color: ${ink}; border-radius: 6px;"><div style="font: 600 13px system-ui, sans-serif;">${title}</div><div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px;">${entries.map(([k, h]) => `<div style="display: flex; flex-direction: column; gap: 3px; font: 10.5px system-ui, sans-serif;"><div style="height: 30px; border-radius: 4px; background: ${h}; border: 1px solid rgba(128,128,128,.25);"></div><div style="font-weight: 500;">${k}</div><div style="font-family: ui-monospace, monospace; opacity: .75;">${h}</div></div>`).join("")}</div></div>`;
  const blocks = [];
  for (const mode of ["light", "dark"]) {
    const t = T.variants[LEAD].themes[mode], P = T.palettes[mode][LEAD];
    blocks.push(cells(`${mode} · surfaces and ink`, Object.entries(t), t.panel, t.ink));
    blocks.push(cells(`${mode} · evidence classes (colour redundant to shape and fill)`, [...Object.entries(P.evidence), ["absent", P.absent]], t.panel, t.ink));
    blocks.push(cells(`${mode} · source slots, fixed order`, P.sources.map((s) => [`${s.slot} ${s.provider}`, s.hex]), t.panel, t.ink));
    blocks.push(cells(`${mode} · status (fixed) and backgrounds`, [...Object.entries(P.status).filter(([k]) => k !== "contrast"), ...Object.entries(P.statusBg).map(([k, h]) => [`${k} bg`, h])], t.panel, t.ink));
  }
  const n = T.night[NIGHT];
  blocks.push(cells(`night · ${n.name}`, [["bg", n.bg], ["panel", n.panel], ["raised", n.raised], ["line", n.line], ["ink", n.ink], ["muted", n.muted], ["faint", n.faint], ["accent", n.accent], ["warn", n.warn], ["bad", n.bad], ...n.sourceLuminance.map((h, i) => [`source lum ${i + 1}`, h])], n.bg, n.ink));
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>
    body { margin: 0; background: #ecece9; }
    a { color: #2a5bd7; } a:hover { color: #1b3f9c; }
  </style>
</helmet>
<div style="width: 1440px; padding: 24px; display: flex; flex-direction: column; gap: 14px; box-sizing: border-box; background: #ecece9;">
  <div style="font: 600 18px system-ui, sans-serif; color: #1b1b1b;">Colour tokens · variant ${LEAD} ${T.variants[LEAD].name} · generated ${T.$meta.generated.slice(0, 10)}</div>
  <div style="font: 12px system-ui, sans-serif; color: #5a5a58;">Every value computed in OKLCH and validated with the dataviz validator against the surface it sits on. Source slots pass every gate in both modes; the six evidence hues cannot pass all-pairs colour vision, so shape and fill carry the class.</div>
  ${blocks.join("\n")}
</div>
</x-dc>
</body>
</html>
`;
}

const files = {
  "Main.dc.html": screen(LEAD, "light"),
  "Dark.dc.html": screen(LEAD, "dark"),
  "Night.dc.html": screen(LEAD, "night"),
  "Tokens.dc.html": sheet(),
  "DirectionB.dc.html": screen("B", "light"),
  "DirectionC.dc.html": screen("C", "light"),
};
for (const [name, html] of Object.entries(files)) writeFileSync(`${OUT}/${name}`, html);
const canvas = {
  artboards: [
    { file: "Main.dc.html", title: `Light · ${T.variants[LEAD].name}`, x: 0, y: 0, w: 1440, h: 900 },
    { file: "Dark.dc.html", title: `Dark · ${T.variants[LEAD].name}`, x: 1540, y: 0, w: 1440, h: 900 },
    { file: "Night.dc.html", title: `Night · ${T.night[NIGHT].name}`, x: 3080, y: 0, w: 1440, h: 900 },
    { file: "Tokens.dc.html", title: "Colour tokens", x: 0, y: 1060, w: 1440, h: 1500 },
    { file: "DirectionB.dc.html", title: "Direction B · Almanac (light)", x: 1540, y: 1060, w: 1440, h: 900 },
    { file: "DirectionC.dc.html", title: "Direction C · Hyperlegible (light)", x: 3080, y: 1060, w: 1440, h: 900 },
  ],
  annotations: [
    { id: "brief", x: 0, y: -160, w: 720, text: `Ticket #41 prototype. Top row: variant ${LEAD} in the three themes. Bottom row: the colour tokens with hex, then variants B and C in light. ${note}; rows marked constructed use the contract's wire shape. Live switching lives in tokens.html on branch prototype/tokens.` },
  ],
  launch: { view: "canvas" },
};
writeFileSync(`${OUT}/canvas.json`, JSON.stringify(canvas, null, 2));
console.log(`wrote ${Object.keys(files).length} artboards to ${OUT} (${note})`);
