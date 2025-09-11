"use client";

import './globals.css'
import Link from 'next/link'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { usePathname } from 'next/navigation'
import { HomeIcon, BookOpenIcon, FolderPlusIcon, ChatBubbleLeftRightIcon, Squares2X2Icon, Bars3Icon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { ToastProvider } from '../components/Toaster'
import { SWRConfig } from 'swr'

const links = [
  { href: '/', label: 'Home', icon: HomeIcon },
  { href: '/courses', label: 'My Courses', icon: BookOpenIcon },
  { href: '/browse', label: 'Browse', icon: Squares2X2Icon },
  { href: '/upload', label: 'Upload Material', icon: FolderPlusIcon },
  { href: '/chat', label: 'Edu Chatbot', icon: ChatBubbleLeftRightIcon },
  // Removed Summarize/MCQ/Flashcards here; available inside individual courses
]

export default function RootLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const isAuthPage = pathname === '/login' || pathname === '/signup'
  // Use SSR-safe defaults; sync from localStorage after mount to avoid hydration mismatch
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [user, setUser] = useState<{ name?: string; email?: string } | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  // Remove initial loader flash by applying class synchronously on mount
  useEffect(() => {
    // On mount, initialize theme from localStorage or current document class
    try{
      const saved = (localStorage.getItem('theme') as 'dark' | 'light' | null)
      const initial = saved ?? (document.documentElement.classList.contains('light') ? 'light' : 'dark')
      setTheme(initial)
      document.documentElement.classList.toggle('light', initial === 'light')
    }catch{}
  }, [])

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.classList.toggle('light', theme === 'light')
      localStorage.setItem('theme', theme)
      // expose setter for children (e.g., settings page)
      ;(window as any).setAppTheme = (mode: 'light'|'dark') => setTheme(mode)
    }
  }, [theme])

  // Simple auth gate: if no JWT, redirect to /login (allow login/signup pages). If JWT present on auth pages, send to home.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const publicPaths = ['/login', '/signup']
    const token = localStorage.getItem('jwt')
    const onAuthPage = publicPaths.includes(pathname || '')
    if (!token && !onAuthPage) {
      window.location.href = '/login'
      return
    }
    if (token && onAuthPage) {
      window.location.href = '/'
    }
  }, [pathname])

  // Parse JWT to populate user menu
  useEffect(() => {
    if (typeof window === 'undefined') return
    const token = localStorage.getItem('jwt')
    if (!token) { setUser(null); return }
    try {
      const parts = token.split('.')
      if (parts.length >= 2){
        const payload = JSON.parse(atob(parts[1].replace(/-/g,'+').replace(/_/g,'/')))
        setUser({ name: payload.name, email: payload.email })
      }
    } catch { setUser(null) }
  }, [pathname])

  function initials(name?: string){
    const n = (name || '').trim()
    if (!n) return 'U'
    const bits = n.split(/\s+/)
    const first = bits[0]?.[0] || ''
    const second = bits[1]?.[0] || ''
    return (first + second).toUpperCase() || 'U'
  }

  function signOut(){
    try{
      localStorage.removeItem('jwt')
      // Best-effort: prevent Google One Tap auto select
      // @ts-ignore
      if (window.google?.accounts?.id?.disableAutoSelect) window.google.accounts.id.disableAutoSelect()
    }catch{}
    if (typeof window !== 'undefined') window.location.href = '/login'
  }

  // Close menu when clicking outside
  useEffect(() => {
    function onDocClick(e: MouseEvent){
      if (!menuRef.current) return
      if (!menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [])

  // Persist sidebar state
  useEffect(() => {
    try { localStorage.setItem('sidebarOpen', String(sidebarOpen)) } catch {}
  }, [sidebarOpen])

  // Sync sidebar state from localStorage after mount to match user preference
  useEffect(() => {
    try {
      const saved = localStorage.getItem('sidebarOpen')
      if (saved !== null) setSidebarOpen(saved === 'true')
    } catch {}
  }, [])

  return (
    <html lang="en">
      <body>
        {/* Prevent theme flicker: set initial class based on localStorage before React mounts */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('theme');if(t==='light'){document.documentElement.classList.add('light')}else{document.documentElement.classList.remove('light')}}catch(e){}",
          }}
        />
        <SWRConfig value={{ fetcher: (url: string) => fetch(url).then(r=>r.json()), revalidateOnFocus: false, dedupingInterval: 1500 }}>
        <ToastProvider>
        {isAuthPage ? (
          // Minimal layout on auth pages: no sidebar or topbar
          <main className="min-h-screen">
            {children}
          </main>
        ) : (
          <div className="min-h-screen flex">
            <aside className={`${sidebarOpen ? 'w-64' : 'w-14 md:w-14'} p-3 border-r border-white/10 bg-card bg-opacity-50 backdrop-blur transition-all duration-200 overflow-hidden`}>
              <div className="flex items-center gap-2 mb-6">
                <button
                  className="w-10 h-10 flex items-center justify-center rounded hover:bg-white/10"
                  onClick={()=>setSidebarOpen(v=>!v)}
                  aria-label="Toggle sidebar"
                  title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
                >
                  <Bars3Icon className="w-6 h-6 shrink-0" />
                </button>
                {sidebarOpen && <div className="text-2xl font-bold">Learnova</div>}
              </div>
              <nav className="space-y-1">
                {links.map(l => (
                  <Link
                    key={l.href}
                    href={l.href}
                    className={clsx(
                      'sidebar-link',
                      sidebarOpen ? 'flex pl-1 pr-3 py-2 gap-2' : 'flex w-10 h-10 items-center justify-center',
                      pathname === l.href && 'active'
                    )}
                  >
                    <span className={clsx('inline-flex items-center justify-center shrink-0', sidebarOpen ? 'w-8 h-8' : 'w-6 h-6') }>
                      <l.icon className="w-6 h-6 shrink-0" />
                    </span>
                    {sidebarOpen && <span>{l.label}</span>}
                  </Link>
                ))}
              </nav>
              {/* Theme toggle moved to Settings page */}
            </aside>
            <main className="flex-1">
              {/* Topbar with search (left) and user menu (right) */}
              <div className="flex items-center justify-between gap-3 p-3 border-b border-white/10 bg-card bg-opacity-30 backdrop-blur sticky top-0 z-40">
                <form className="hidden md:flex items-center bg-white/5 rounded-full px-3 py-2 w-[420px] border border-white/10">
                  <input className="bg-transparent outline-none flex-1 text-sm" placeholder="Search courses, topics, or anything..." />
                </form>
                {user && (
                  <div className="relative" ref={menuRef}>
                    <button
                      aria-label="User menu"
                      className="w-9 h-9 rounded-full bg-blue-500/30 border border-white/20 flex items-center justify-center text-sm font-semibold hover:bg-blue-500/40"
                      onClick={(e)=>{ e.stopPropagation(); setMenuOpen(v=>!v) }}
                      title={user.email}
                    >
                      {initials(user.name)}
                    </button>
                    {menuOpen && (
                      <div className="absolute right-0 mt-2 w-44 rounded-md border border-white/10 bg-card shadow-lg z-50">
                        <Link href="/profile" className="block px-3 py-2 text-sm hover:bg-white/10">Profile</Link>
                        <Link href="/settings" className="block px-3 py-2 text-sm hover:bg-white/10">Settings</Link>
                        <button className="w-full text-left px-3 py-2 text-sm hover:bg-white/10" onClick={signOut}>Sign out</button>
                      </div>
                    )}
                  </div>
                )}
              </div>
              {children}
            </main>
          </div>
        )}
        </ToastProvider>
        </SWRConfig>
      </body>
    </html>
  )
}
