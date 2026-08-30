import { renderHook, act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { initialTheme, THEME_STORAGE_KEY, useTheme } from './theme'

describe('weather desk theme', () => {
  const values = new Map<string, string>()
  beforeEach(() => {
    values.clear()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      clear: () => values.clear(),
    })
    delete document.documentElement.dataset.theme
  })

  it('follows the system when no explicit choice was initialized in the head', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    expect(initialTheme()).toBe('dark')
    vi.unstubAllGlobals()
  })

  it('persists an explicit choice and updates the document theme', () => {
    document.documentElement.dataset.theme = 'dark'
    const { result } = renderHook(() => useTheme())
    act(() => result.current.setTheme('light'))
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
