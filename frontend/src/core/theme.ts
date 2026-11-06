/** The looks one can choose. A person's choice follows them from the server; the browser
 *  remembers the last one, so the login page has it too. */
export const THEMES = [
  ['dark', 'Mørk'],
  ['win7', 'Windows 7'],
  ['winxp', 'Windows XP'],
  ['win2k', 'Windows 2000'],
  ['vs-blue', 'VS 2017 Blå'],
  ['vs-dark', 'VS 2017 Mørk'],
  ['vs-light', 'VS 2017 Lys'],
] as const

export type Theme = (typeof THEMES)[number][0]

const KEY = 'slq-theme'
const known = (id: string | null | undefined): id is Theme => THEMES.some(([key]) => key === id)

export function savedTheme(): Theme {
  try {
    const id = localStorage.getItem(KEY)
    return known(id) ? id : 'dark'
  } catch {
    return 'dark'
  }
}

/** Show a theme and remember it here. Returns what is shown, for an unknown id the old one. */
export function showTheme(id: string | null | undefined): Theme {
  const theme = known(id) ? id : savedTheme()
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // a browser that keeps nothing still shows it
  }
  return theme
}
