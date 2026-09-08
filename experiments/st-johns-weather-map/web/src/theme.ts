import { useEffect, useState } from 'react'
import type { Theme } from './mapStyle'

export const THEME_STORAGE_KEY = 'astraeus-weather-theme'

export function initialTheme(): Theme {
  const fromDocument = document.documentElement.dataset.theme
  if (fromDocument === 'light' || fromDocument === 'dark' || fromDocument === 'night') return fromDocument
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(initialTheme)
  const setTheme = (next: Theme) => {
    try { localStorage.setItem(THEME_STORAGE_KEY, next) } catch { /* Browser preference may be unavailable. */ }
    setThemeState(next)
  }

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme === 'light' ? 'light' : 'dark'
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f2efe7' : theme === 'dark' ? '#07151c' : '#000000')
  }, [theme])

  return { theme, setTheme }
}
