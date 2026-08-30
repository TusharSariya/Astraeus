# Avalon Evidence Desk web experiment

An isolated, non-operational React workbench for the St. John's weather-map
proof of concept. It calls `/api/experiments/weather/v0/point` and fails closed
to unavailable evidence when the API cannot be read.

```sh
npm install
npm run dev
```

The normal UI fails closed to unavailable evidence if the API cannot be read.
For deliberate fixture demonstrations only, start the development server with
`VITE_WEATHER_FIXTURES=true npm run dev`; persistent fixture watermarks are then
shown throughout the evidence UI. This opt-in is ignored in production builds.

Use `npm test` for interaction tests and `npm run build` for the production
bundle check. GPS is never requested on page load; the browser prompt is only
opened by the **Use my location** button.

This is an experiment, not an Astraeus V1 production implementation or an
operational weather, warning, marine-navigation, or calibrated-probability
product.
