import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: process.env.WEATHER_API_PROXY_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: false } } },
  test: {
    // Two projects, because one of them needs something jsdom cannot provide.
    // `unit` is everything that has always run here. `gl` exists because jsdom
    // has no WebGL, so the shader strings were never handed to a compiler by
    // anything except a user's browser - which is how a fragment shader that
    // could not compile shipped and drew nothing while the map disclosed that
    // it had advected. It runs in the default `npm test` gate deliberately: a
    // silently dead renderer is not the class of bug that belongs behind an
    // opt-in target.
    projects: [
      {
        extends: true,
        test: {
          name: 'unit',
          environment: 'jsdom',
          setupFiles: './src/test/setup.ts',
          include: ['src/**/*.test.{ts,tsx}'],
          exclude: ['src/**/*.browser.test.{ts,tsx}', 'src/e2e/**'],
          css: true,
        },
      },
      {
        extends: true,
        test: {
          name: 'gl',
          include: ['src/**/*.browser.test.{ts,tsx}'],
          browser: {
            enabled: true,
            headless: true,
            provider: 'playwright',
            // The installed Chrome, not a downloaded Chromium: this asserts
            // GLSL against the same compiler a reader's browser uses, and keeps
            // the toolchain from pulling a second browser binary into the repo.
            providerOptions: { launch: { channel: 'chrome' } },
            instances: [{ browser: 'chromium' }],
          },
        },
      },
      // `e2e` is the third project (plan H3): the real App, in real Chrome,
      // against the real API, reading the MapLibre canvas back. It exists ONLY
      // under VITE_E2E=1, for two reasons - it needs a stack running on
      // localhost:8000 (the suite skips itself when nothing answers), and the
      // same flag is what turns on `preserveDrawingBuffer` in MapPanel, which
      // costs every reader a compositing step and so is never on in a build a
      // reader gets. Absent the flag `npm test` is exactly the two projects
      // above.
      ...(process.env.VITE_E2E === '1'
        ? [{
            extends: true as const,
            test: {
              name: 'e2e',
              include: ['src/e2e/**/*.e2e.test.{ts,tsx}'],
              testTimeout: 180_000,
              browser: {
                enabled: true,
                headless: true,
                provider: 'playwright' as const,
                instances: [{ browser: 'chromium' }],
              },
            },
          }]
        : []),
    ],
  },
})
