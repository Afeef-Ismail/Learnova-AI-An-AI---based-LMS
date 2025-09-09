"use client";

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Pos = { top: number; left: number }

export function KebabMenu({ buttonClassName = '', children }: { buttonClassName?: string; children: ReactNode }){
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<Pos | null>(null)
  const anchorRef = useRef<HTMLButtonElement | null>(null)
  const portalRef = useRef<HTMLDivElement | null>(null)
  const localWrapRef = useRef<HTMLDivElement | null>(null)

  // Position the menu under the anchor, aligned to right edge, with viewport clamping
  function computePos(){
    const btn = anchorRef.current
    if(!btn) return null
    const rect = btn.getBoundingClientRect()
    const menuW = 192 // w-48
    const gap = 8
    const maxLeft = window.innerWidth - menuW - 8
    const desiredLeft = rect.right - menuW
    const left = Math.max(8, Math.min(maxLeft, desiredLeft))
    const top = Math.min(window.innerHeight - 8, rect.bottom + gap)
    return { top, left }
  }

  useEffect(() => {
    if(!open) return
    const p = computePos()
    if(p) setPos(p)
    function onWin(){ const np = computePos(); if(np) setPos(np) }
    window.addEventListener('scroll', onWin, true)
    window.addEventListener('resize', onWin)
    return () => {
      window.removeEventListener('scroll', onWin, true)
      window.removeEventListener('resize', onWin)
    }
  }, [open])

  // Close on outside click (consider both anchor and portal menu)
  useEffect(() => {
    function onDoc(e: MouseEvent){
      const target = e.target as Node
      const inAnchor = !!localWrapRef.current && localWrapRef.current.contains(target)
      const inPortal = !!portalRef.current && portalRef.current.contains(target)
      if(!inAnchor && !inPortal) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const menu = open && pos ? (
    <div ref={portalRef} style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 9999 }}>
      <div className="w-48 bg-card border border-white/10 rounded-lg shadow-lg" onClick={()=>setOpen(false)}>
        {children}
      </div>
    </div>
  ) : null

  return (
    <div className="relative" ref={localWrapRef}>
      <button ref={anchorRef} className={buttonClassName || 'px-2 py-1 rounded hover:bg-white/10'} onClick={(e)=>{ e.preventDefault(); e.stopPropagation(); setOpen(v=>!v) }} aria-label="Open menu">⋯</button>
      {menu && createPortal(menu, document.body)}
    </div>
  )
}
