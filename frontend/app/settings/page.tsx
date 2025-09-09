"use client";
import { useEffect, useState } from 'react'

export default function SettingsPage(){
  const [theme, setTheme] = useState<'dark'|'light'>(typeof document !== 'undefined' && document.documentElement.classList.contains('light') ? 'light' : 'dark')

  useEffect(() => {
    // Keep UI in sync if user toggles elsewhere
    const isLight = document.documentElement.classList.contains('light')
    setTheme(isLight ? 'light' : 'dark')
  }, [])

  function toggleTheme(){
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    // call layout setter exposed on window to ensure consistent state
    if (typeof window !== 'undefined' && (window as any).setAppTheme){
      (window as any).setAppTheme(next)
    }
  }

  return (
    <div className="container py-8 space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <div className="card p-4 flex items-center justify-between">
        <div>
          <div className="font-medium">Theme</div>
          <div className="text-sm text-muted">Switch between light and dark mode</div>
        </div>
        <button className="btn btn-outline" onClick={toggleTheme}>
          Toggle to {theme === 'dark' ? 'Light' : 'Dark'} Mode
        </button>
      </div>

      <div className="card p-4">
        <div className="font-medium mb-2">Profile & Preferences</div>
        <div className="text-sm text-muted">Additional settings can go here (language, notifications, etc.).</div>
      </div>
    </div>
  )
}
