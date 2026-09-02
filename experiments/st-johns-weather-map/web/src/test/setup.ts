import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'

// Node 26 ships its own `localStorage` global that shadows jsdom's and throws
// unless the runtime was started with --localstorage-file. Every read and write
// in the app is wrapped in try/catch (they are display preferences, not
// evidence), so nothing crashed - but the catch swallowed it silently, which
// made every "remembers the choice across sessions" assertion vacuous: the
// second render simply started from the default again and the test passed for
// the wrong reason. An in-memory store restores the behaviour a browser has.
class MemoryStorage implements Storage {
  private entries = new Map<string, string>()
  get length(): number { return this.entries.size }
  key(index: number): string | null { return [...this.entries.keys()][index] ?? null }
  getItem(key: string): string | null { return this.entries.get(key) ?? null }
  setItem(key: string, value: string): void { this.entries.set(key, String(value)) }
  removeItem(key: string): void { this.entries.delete(key) }
  clear(): void { this.entries.clear() }
}

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  writable: true,
  value: new MemoryStorage(),
})

// Per test, so one test's remembered preference cannot leak into the next.
// Tests that need persistence ACROSS renders keep it within their own body.
beforeEach(() => localStorage.clear())
afterEach(() => cleanup())
