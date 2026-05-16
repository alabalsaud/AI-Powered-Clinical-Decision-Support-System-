/** Persisted UI theme: dark (default) or light */
export const THEME_KEY = 'cdss_theme';

export function getStoredTheme() {
  if (typeof window === 'undefined') return 'dark';
  const v = localStorage.getItem(THEME_KEY);
  return v === 'light' ? 'light' : 'dark';
}

export function applyTheme(mode) {
  const m = mode === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = m;
  try {
    localStorage.setItem(THEME_KEY, m);
  } catch {
    /* ignore quota / private mode */
  }
}
