"use client";

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { API_BASE, apiPost, apiGet } from '../../../../lib/api'
import { FlipCard } from '../../../../components/FlipCard'
import { Spinner } from '../../../../components/Spinner'
import { useToast } from '../../../../components/Toaster'

type FCItem = { id: number; question: string; answer: string; box: number; due_at: string }

export default function CourseFlashcardsAll(){
  const params = useParams()
  const id = decodeURIComponent(params?.id as string)
  const [items, setItems] = useState<FCItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [generating, setGenerating] = useState(false)
  const { push } = useToast()
  const [error, setError] = useState<string | null>(null)
  const [box, setBox] = useState<number | null>(null)
  const [boxCounts, setBoxCounts] = useState<Record<number, number>>({})
  // Grouped view (All): per-box state
  const [groupItems, setGroupItems] = useState<Record<number, FCItem[]>>({1:[],2:[],3:[],4:[],5:[]})
  const [groupTotals, setGroupTotals] = useState<Record<number, number>>({1:0,2:0,3:0,4:0,5:0})
  const [groupLoading, setGroupLoading] = useState(false)
  const [groupLoadingMore, setGroupLoadingMore] = useState<Record<number, boolean>>({})
  const [flippedMap, setFlippedMap] = useState<Record<number, boolean>>({})
  const toggleFlip = (id: number) => setFlippedMap(prev => ({ ...prev, [id]: !prev[id] }))

  const limit = 24
  async function load(reset: boolean){
    if(!id) return
    if(reset) setLoading(true); else setLoadingMore(true)
    try{
      setError(null)
      const offset = reset ? 0 : items.length
      const boxParam = box != null ? `&box=${box}` : ''
      const res = await fetch(`${API_BASE}/flashcards/list?course_id=${encodeURIComponent(id)}&limit=${limit}&offset=${offset}${boxParam}`).then(r=>r.json())
      if(res?.status && res.status !== 'ok'){
        setError(res.status)
      }
      if(reset){
        setItems(res.items || [])
      }else{
        setItems(prev => [...prev, ...((res.items)||[])])
      }
      setTotal(res.total || 0)
    }finally{
      setLoading(false); setLoadingMore(false)
    }
  }

  // Grouped loaders for All view
  const groupLimit = 12
  async function loadGroupInitial(){
    if(!id) return
    setGroupLoading(true)
    try{
      const boxes = [1,2,3,4,5]
      const results = await Promise.allSettled(
        boxes.map(b => fetch(`${API_BASE}/flashcards/list?course_id=${encodeURIComponent(id)}&limit=${groupLimit}&offset=0&box=${b}`)
          .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
        )
      )
      const itemsMap: Record<number, FCItem[]> = {1:[],2:[],3:[],4:[],5:[]}
      const totalsMap: Record<number, number> = {1:0,2:0,3:0,4:0,5:0}
      results.forEach((res, idx) => {
        const b = [1,2,3,4,5][idx]
        if(res.status === 'fulfilled'){
          const data = res.value || {}
          itemsMap[b] = data.items || []
          totalsMap[b] = data.total || 0
        } else {
          // leave defaults; optionally surface in console
          console.warn('Failed to load box', b, res.reason)
        }
      })
      setGroupItems(itemsMap)
      setGroupTotals(totalsMap)
    } finally {
      setGroupLoading(false)
    }
  }

  async function loadGroupMore(b: number){
    if(!id) return
    setGroupLoadingMore(prev => ({...prev, [b]: true}))
    try{
      const offset = groupItems[b]?.length || 0
      const res = await fetch(`${API_BASE}/flashcards/list?course_id=${encodeURIComponent(id)}&limit=${groupLimit}&offset=${offset}&box=${b}`).then(r=>r.json())
      setGroupItems(prev => ({...prev, [b]: [...(prev[b]||[]), ...((res.items)||[])]}))
      setGroupTotals(prev => ({...prev, [b]: res.total || prev[b] || 0}))
    } finally {
      setGroupLoadingMore(prev => ({...prev, [b]: false}))
    }
  }

  async function generateMore(){
    if(!id) return
    setGenerating(true)
    try{
      const res = await apiPost<{ ok: boolean; created?: number; skipped?: number }>(
        '/flashcards/generate', { course_id: id }
      )
      const created = res?.created ?? 0
      const skipped = res?.skipped ?? 0
      push({ message: `Generated ${created} new, skipped ${skipped} duplicates`, kind: 'success' })
      await refreshCounts()
      if(box === null){
        await loadGroupInitial()
      } else {
        await load(true)
      }
    }catch(e:any){
      push({ message: e.message || 'Failed to generate', kind: 'error' })
    }finally{ setGenerating(false) }
  }

  useEffect(()=>{
    if(!id) return
    if(box === null){
      loadGroupInitial()
    } else {
      load(true)
    }
  }, [id, box])

  async function refreshCounts(){
    try{
      const stats = await apiGet<{ counts: Record<number, number> }>(`/flashcards/stats?course_id=${encodeURIComponent(id)}`)
      setBoxCounts(stats.counts || {})
    }catch{}
  }
  useEffect(()=>{ if(id) refreshCounts() }, [id])

  const canLoadMore = items.length < total

  return (
    <div className="container py-8 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href={`/courses/${encodeURIComponent(id)}?tab=flashcards`} aria-label="Back to flashcards" className="btn btn-outline px-3 py-1">←</Link>
          <h1 className="text-2xl font-semibold">Flashcards for: {id}</h1>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-outline" onClick={generateMore} disabled={generating}>{generating ? (<><Spinner size={16} /> <span className="ml-2">Generating…</span></>) : 'Generate More'}</button>
          <Link href={`/courses/${encodeURIComponent(id)}?tab=flashcards`} className="btn btn-outline">Back to Course</Link>
        </div>
      </div>

  {loading && <div className="text-muted">Loading…</div>}
  {error && <div className="text-red-400 text-sm">{error}</div>}

      <div className="flex gap-2 border-b border-white/10 pb-2">
        {[null,1,2,3,4,5].map(b => (
          <button key={String(b)} className={`px-3 py-1 rounded ${box===b ? 'bg-white/10' : 'hover:bg-white/10'}`} onClick={()=>{ setItems([]); setTotal(0); setBox(b) }}>
            {b===null ? 'All' : `Box ${b}`}
            {b===null ? (
              (() => { const totalCount = Object.values(boxCounts||{}).reduce((a,b)=>a+(b||0),0); return (
                <span className="ml-2 text-xs bg-white/10 rounded-full px-2 py-0.5">{totalCount}</span>
              ) })()
            ) : (
              boxCounts[b] ? <span className="ml-2 text-xs bg-white/10 rounded-full px-2 py-0.5">{boxCounts[b]}</span> : null
            )}
          </button>
        ))}
      </div>

      {box === null ? (
        <div className="space-y-8 mt-4">
          {[1,2,3,4,5].map(b => {
            const itemsB = groupItems[b] || []
            const totalB = groupTotals[b] || 0
            const canMore = itemsB.length < totalB
            return (
              <section key={b}>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-lg font-semibold">Box {b} {typeof boxCounts[b] === 'number' ? <span className="ml-2 text-xs bg-white/10 rounded-full px-2 py-0.5">{boxCounts[b]}</span> : null}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {itemsB.map(fc => (
                    <FlipCard key={fc.id}
                      flipped={!!flippedMap[fc.id]}
                      onToggle={() => toggleFlip(fc.id)}
                      front={<div className="card p-4 h-full flex items-center justify-center"><div className="font-medium leading-relaxed text-center">{fc.question}</div></div>}
                      back={<div className="card p-4 h-full flex items-center justify-center"><div className="font-medium leading-relaxed text-center max-h-full overflow-y-auto pr-1">{fc.answer}</div></div>}
                    />
                  ))}
                  {!groupLoading && !itemsB.length && <div className="text-muted">No cards in this box.</div>}
                </div>
                <div className="flex justify-center mt-3">
                  <button className="btn btn-outline" onClick={()=>loadGroupMore(b)} disabled={!canMore || !!groupLoadingMore[b]}>
                    {groupLoadingMore[b] ? (<><Spinner size={16} /> <span className="ml-2">Loading…</span></>) : 'Load More'}
                  </button>
                </div>
              </section>
            )
          })}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
            {items.map((fc) => (
              <FlipCard key={fc.id}
                flipped={!!flippedMap[fc.id]}
                onToggle={() => toggleFlip(fc.id)}
                front={<div className="card p-4 h-full flex items-center justify-center"><div className="font-medium leading-relaxed text-center">{fc.question}</div></div>}
                back={<div className="card p-4 h-full flex items-center justify-center"><div className="font-medium leading-relaxed text-center max-h-full overflow-y-auto pr-1">{fc.answer}</div></div>}
              />
            ))}
            {!loading && !items.length && <div className="text-muted">No flashcards yet. Click Generate More.</div>}
          </div>
          <div className="flex justify-center">
            <button className="btn btn-outline" onClick={()=>load(false)} disabled={!canLoadMore || loadingMore}>
              {loadingMore ? (<><Spinner size={16} /> <span className="ml-2">Loading…</span></>) : 'Load More Flashcards'}
            </button>
          </div>
        </>
      )}

      <div className="flex justify-center">
        <Link href="/courses" className="btn btn-outline">Back to My Courses</Link>
      </div>
    </div>
  )
}
