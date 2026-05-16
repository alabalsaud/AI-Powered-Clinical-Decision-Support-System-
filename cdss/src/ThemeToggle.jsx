import { useState, useCallback } from 'react';
import { getStoredTheme, applyTheme } from './theme.js';

export default function ThemeToggle({ className = '' }) {
  const [mode, setMode] = useState(() => getStoredTheme());

  const toggle = useCallback(() => {
    const next = mode === 'dark' ? 'light' : 'dark';
    setMode(next);
    applyTheme(next);
  }, [mode]);

  return (
    <button
      type="button"
      className={`theme-toggle${className ? ` ${className}` : ''}`}
      onClick={toggle}
      title={mode === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      aria-label={mode === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      {mode === 'dark' ? '☀️' : '🌙'}
    </button>
  );
}
