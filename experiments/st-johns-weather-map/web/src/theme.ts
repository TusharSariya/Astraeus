import { useEffect, useState } from 'react'
import type { Theme } from './mapStyle'

export const THEME_STORAGE_KEY = 'astraeus-weather-theme'

export function initialTheme(): Theme {
  const fromDocument = document.documentElement.dataset.theme
  if (fromDocument === 'light' || fromDocument === 'dark') return fromDocument
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(initialTheme)
  const setTheme = (next: Theme) => {
    localStorage.setItem(THEME_STORAGE_KEY, next)
    setThemeState(next)
  }

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#07151C' : '#F2EFE7')
  }, [theme])

  return { theme, setTheme }
}
