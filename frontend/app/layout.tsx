"use client";

import './globals.css'
import Link from 'next/link'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { usePathname } from 'next/navigation'
import { HomeIcon, BookOpenIcon, FolderPlusIcon, ChatBubbleLeftRightIcon, Squares2X2Icon, QuestionMarkCircleIcon, RectangleStackIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { ToastProvider } from '../components/Toaster'
import { SWRConfig } from 'swr'

const links = [
  { href: '/', label: 'Home', icon: HomeIcon },
  { href: '/courses', label: 'My Courses', icon: BookOpenIcon },
  { href: '/browse', label: 'Browse', icon: Squares2X2Icon },
  { href: '/upload', label: 'Upload Material', icon: FolderPlusIcon },
  { href: '/chat', label: 'Edu Chatbot', icon: ChatBubbleLeftRightIcon },
  { href: '/summarize', label: 'Summarize', icon: Squares2X2Icon },
  { href: '/mcq', label: 'MCQ Practice', icon: QuestionMarkCircleIcon },
  { href: '/flashcards', label: 'Flashcards', icon: RectangleStackIcon },
]

export default function RootLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [user, setUser] = useState<{ name?: string; email?: string } | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? (localStorage.getItem('theme') as 'dark' | 'light' | null) : null
    if (saved) setTheme(saved)
  }, [])

  useEffect(() => {
    if (typeof document !== 'undefined') {
      if (theme === 'light') document.documentElement.classList.add('light')
      else document.documentElement.classList.remove('light')
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

  return (
    <html lang="en">
      <body>
        <SWRConfig value={{ fetcher: (url: string) => fetch(url).then(r=>r.json()), revalidateOnFocus: false, dedupingInterval: 1500 }}>
        <ToastProvider>
        <div className="min-h-screen grid grid-cols-12">
          <aside className="col-span-2 p-4 border-r border-white/10 bg-card bg-opacity-50 backdrop-blur">
            <div className="text-2xl font-bold mb-6">Learnova</div>
            <nav className="space-y-1">
              {links.map(l => (
                <Link key={l.href} href={l.href} className={clsx('sidebar-link', pathname === l.href && 'active')}>
                  <l.icon className="w-5 h-5" />
                  <span>{l.label}</span>
                </Link>
              ))}
            </nav>
            {/* Theme toggle moved to Settings page */}
          </aside>
          <main className="col-span-10">
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
                      <a href="/profile" className="block px-3 py-2 text-sm hover:bg-white/10">Profile</a>
                      <a href="/settings" className="block px-3 py-2 text-sm hover:bg-white/10">Settings</a>
                      <button className="w-full text-left px-3 py-2 text-sm hover:bg-white/10" onClick={signOut}>Sign out</button>
                    </div>
                  )}
                </div>
              )}
            </div>
            {children}
          </main>
        </div>
        </ToastProvider>
        </SWRConfig>
      </body>
    </html>
  )
}
