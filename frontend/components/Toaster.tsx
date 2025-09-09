"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

type Toast = { id: number; message: string; kind?: 'info'|'success'|'error' }
const Ctx = createContext<{ toasts: Toast[]; push: (t: Omit<Toast,'id'>)=>void } | null>(null)

export function ToastProvider({ children }: { children: ReactNode }){
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((t: Omit<Toast,'id'>) => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, ...t }])
    setTimeout(() => setToasts(prev => prev.filter(x => x.id !== id)), 2500)
  }, [])
  const value = useMemo(() => ({ toasts, push }), [toasts, push])
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 space-y-2 z-50">
        {toasts.map(t => (
          <div key={t.id} className={`px-3 py-2 rounded-lg shadow-card border text-sm ${t.kind==='error' ? 'bg-red-500/20 border-red-400/30' : t.kind==='success' ? 'bg-emerald-500/20 border-emerald-400/30' : 'bg-white/10 border-white/20'}`}>{t.message}</div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

export function useToast(){
  const ctx = useContext(Ctx)
  if(!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
