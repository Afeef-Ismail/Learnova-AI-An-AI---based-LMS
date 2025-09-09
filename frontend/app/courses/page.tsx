"use client";

import useSWR from 'swr'
import Link from 'next/link'
import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../../lib/api'
import { apiDelete } from '../../lib/api'
import { KebabMenu } from '../../components/KebabMenu'
import { useToast } from '../../components/Toaster'
import { Skeleton } from '../../components/Skeleton'

const fetcher = (url: string) => fetch(url).then(r => r.json())

export default function Courses(){
  const { data, error, isLoading, mutate } = useSWR(`${API_BASE}/courses`, fetcher)
  const list = data?.courses || []
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const menuRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const { push } = useToast()

  useEffect(() => {
    function onClick(e: MouseEvent){
      // Close if clicking outside any open menu
      if(!openMenu) return
      const ref = menuRefs.current[openMenu]
      if(ref && !ref.contains(e.target as Node)){
        setOpenMenu(null)
      }
    }
    window.addEventListener('click', onClick)
    return () => window.removeEventListener('click', onClick)
  }, [openMenu])

  return (
    <div className="container py-8">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">My Courses</h1>
        <Link href="/upload" className="btn btn-primary">Create New Course</Link>
      </div>
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Array.from({length:6}).map((_,i)=> (
            <div key={i} className="card p-4">
              <Skeleton className="h-5 w-40 mb-3" />
              <Skeleton className="h-4 w-28" />
            </div>
          ))}
        </div>
      )}
      {error && <p className="text-red-400">Failed to load</p>}
  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative">
        {list.map((c: any) => (
          <div key={c.id} className="card p-4 space-y-2 overflow-visible">
            <div className="flex items-center justify-between">
              <Link href={`/courses/${encodeURIComponent(c.id)}`} className="block">
                <div className="font-medium">{c.id}</div>
                <div className="text-sm text-muted">Open course</div>
              </Link>
              <div className="relative" ref={(el: HTMLDivElement | null) => { menuRefs.current[c.id] = el }}>
                <KebabMenu>
                  <button className="w-full text-left px-3 py-2 hover:bg-white/10" onClick={(e)=>{
                    e.preventDefault(); e.stopPropagation();
                    const url = `${window.location.origin}/courses/${encodeURIComponent(c.id)}`
                    if((navigator as any).share){ (navigator as any).share({ title: 'Learnova Course', url }).catch(()=>{}) }
                    else { navigator.clipboard?.writeText(url); push({ message: 'Link copied', kind: 'success' }) }
                    setOpenMenu(null)
                  }}>Share</button>
                  <button className="w-full text-left px-3 py-2 text-red-400 hover:bg-white/10" onClick={async (e)=>{
                    e.preventDefault(); e.stopPropagation();
                    const ok = confirm(`Delete course "${c.id}"?`)
                    if(!ok) return
                    await apiDelete(`/courses/${encodeURIComponent(c.id)}`)
                    setOpenMenu(null)
                    mutate()
                    push({ message: 'Course deleted', kind: 'success' })
                  }}>Delete</button>
                </KebabMenu>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
