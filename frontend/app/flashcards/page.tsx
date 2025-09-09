"use client";

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { apiGet, apiPost } from '../../lib/api'
import { useToast } from '../../components/Toaster'
import { Skeleton } from '../../components/Skeleton'

type Stats = { due?: number; counts?: Record<number, number> }
const statsFetcher = (p: string) => apiGet(p) as Promise<Stats>

export default function FlashcardsPage(){
  const [courseId, setCourseId] = useState('')
  const [card, setCard] = useState<any>(null)
  const [reveal, setReveal] = useState(false)
  const { data: stats, mutate: refetchStats } = useSWR<Stats>(courseId ? `/flashcards/stats?course_id=${encodeURIComponent(courseId)}` : null, statsFetcher)
  const { push } = useToast()

  async function generate(){
    if(!courseId) return
    await apiPost('/flashcards/generate', { course_id: courseId })
    await refetchStats()
    push({ message: 'Flashcards generated', kind: 'success' })
  }
  async function next(){
    if(!courseId) return
    const res = await apiGet(`/flashcards/next?course_id=${encodeURIComponent(courseId)}&reveal=true`)
    setCard(res)
  }
  async function grade(correct: boolean){
    if(!courseId || !card?.id) return
    await apiPost('/flashcards/grade', { course_id: courseId, flashcard_id: card.id, correct })
    await refetchStats()
    // fetch next due automatically
    const res = await apiGet(`/flashcards/next?course_id=${encodeURIComponent(courseId)}&reveal=true`)
    setCard(res)
    push({ message: correct ? 'Marked Correct' : 'Marked Incorrect', kind: correct ? 'success' : 'info' })
  }

  useEffect(()=>{ setCard(null) }, [courseId])
  useEffect(() => {
    try{
      const saved = localStorage.getItem('lastCourseId')
      if(saved) setCourseId(saved)
    }catch{}
  }, [])
  useEffect(() => {
    try{ if(courseId) localStorage.setItem('lastCourseId', courseId) }catch{}
  }, [courseId])

  return (
    <div className="container py-8 space-y-6">
      <h1 className="text-2xl font-semibold">Flashcards</h1>

      <div className="card p-4 flex gap-2 items-center">
        <input className="bg-card border border-white/20 rounded px-3 py-2 flex-1" placeholder="Enter course id" value={courseId} onChange={e=>setCourseId(e.target.value)} />
        <button className="btn btn-outline" onClick={()=>setReveal(!reveal)} disabled={!courseId}>{reveal ? 'Hide Answer' : 'Show Answer'}</button>
        <button className="btn btn-primary" onClick={next} disabled={!courseId}>Next</button>
        <button className="btn btn-outline" onClick={generate} disabled={!courseId}>Generate</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <div className="card p-6 min-h-[180px]">
            {!card && (
              <div className="text-muted">
                <div>No card loaded. Click Next.</div>
                <div className="mt-3 flex gap-2">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-48" />
                </div>
              </div>
            )}
            {card && card.status === 'empty' && <div className="text-muted">No flashcards yet. Click Generate to create some.</div>}
            {card && card.status === 'ok' && (
              <div className="space-y-3">
                <div className="font-semibold">{card.question}</div>
                {reveal && <div className="text-sm text-muted">Answer: {card.answer}</div>}
                <div className="flex gap-2 pt-2">
                  <button className="btn btn-outline" onClick={()=>grade(false)}>Incorrect</button>
                  <button className="btn btn-primary" onClick={()=>grade(true)}>Correct</button>
                </div>
              </div>
            )}
          </div>
        </div>
        <div>
          <div className="card p-4">
            <div className="font-medium mb-2">Stats</div>
      {!stats && <div className="text-muted text-sm">No data</div>}
      {stats && (
              <div className="space-y-1 text-sm">
        <div>Due now: <span className="font-semibold">{stats?.due ?? 0}</span></div>
                <div className="grid grid-cols-5 gap-2">
                  {[1,2,3,4,5].map(i => (
                    <div key={i} className="text-center p-2 bg-white/5 rounded">
                      <div className="text-xs text-muted">Box {i}</div>
            <div className="font-semibold">{(stats?.counts||{})[i] ?? 0}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
