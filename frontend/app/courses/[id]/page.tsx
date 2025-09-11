"use client";

import useSWR from 'swr'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import type React from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import Image from 'next/image'
import { useToast } from '../../../components/Toaster'
import { Spinner } from '../../../components/Spinner'
import { FlipCard } from '../../../components/FlipCard'
import { API_BASE, apiDelete, apiGet, apiPost } from '../../../lib/api'
import Link from 'next/link'

const fetcher = (url: string) => fetch(url).then(r => r.json())

export default function CourseDetail(){
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const id = decodeURIComponent(params?.id as string)

  const tabs = useMemo(() => [
    { key: 'materials', label: 'Materials' },
    { key: 'youtube', label: 'YouTube' },
    { key: 'mcq', label: 'MCQ' },
    { key: 'flashcards', label: 'Flashcards' },
    { key: 'chat', label: 'Chat' },
    { key: 'summary', label: 'Summary' },
  ] as const, [])
  type TabKey = typeof tabs[number]['key']
  const [tab, setTab] = useState<TabKey>('materials')
  const [menuOpen, setMenuOpen] = useState(false)
  const headerMenuRef = useRef<HTMLDivElement | null>(null)
  const { push } = useToast()

  const { data: files, mutate: refetchFiles } = useSWR(id ? `${API_BASE}/materials?course_id=${id}` : null, fetcher)
  const { data: yt, mutate: refetchYt } = useSWR(id ? `${API_BASE}/materials/youtube?course_id=${id}` : null, fetcher)

  // Close header menu on outside click
  useEffect(() => {
    function onDocClick(e: MouseEvent){
      if(!menuOpen) return
      if(headerMenuRef.current && !headerMenuRef.current.contains(e.target as Node)){
        setMenuOpen(false)
      }
    }
    window.addEventListener('click', onDocClick)
    return () => window.removeEventListener('click', onDocClick)
  }, [menuOpen])

  // Initial tab: prefer ?tab=... if present, otherwise localStorage; default to 'materials'
  useEffect(() => {
    try{
      const k = `course_tab:${id}`
      const param = (searchParams?.get('tab') || '').toLowerCase() as TabKey
  const valid = ['materials','youtube','mcq','flashcards','chat','summary'] as const
      if(param && (valid as readonly string[]).includes(param)){
        setTab(param as TabKey)
        if(typeof window !== 'undefined') window.localStorage.setItem(k, param)
        return
      }
      const saved = (typeof window !== 'undefined') ? window.localStorage.getItem(k) as TabKey | null : null
      if(saved && (valid as readonly string[]).includes(saved)) setTab(saved as TabKey)
      else setTab('materials')
    }catch{}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])
  useEffect(() => {
    try{
      const k = `course_tab:${id}`
      if(typeof window !== 'undefined') window.localStorage.setItem(k, tab)
    }catch{}
  }, [id, tab])

  // Summary
  const [summary, setSummary] = useState<string>("")
  const [sumLoading, setSumLoading] = useState(false)
  async function runSummarize(){
    setSumLoading(true)
    try{
      const res = await apiPost<any>('/summaries/course', { course_id: id })
      setSummary(res?.summary || JSON.stringify(res))
    }catch(e:any){ setSummary(e.message) }
    finally{ setSumLoading(false) }
  }

  // MCQ
  const [mcq, setMcq] = useState<any>(null)
  const [mcqError, setMcqError] = useState<string>("")
  const [mcqLoading, setMcqLoading] = useState(false)
  async function mcqNext(){
    setMcqError("")
    setMcqLoading(true)
    try{
      const q = await apiPost<any>('/mcq/next', { course_id: id })
      setMcq(q)
    }catch(e:any){ setMcq(null); setMcqError(e.message || 'Failed to generate question') }
    finally{ setMcqLoading(false) }
  }
  async function mcqAnswer(idx: number){
    if(!mcq) return
    try{
      const res = await apiPost<any>('/mcq/answer', { course_id: id, question_id: mcq.id, selected_index: idx })
      setMcq({ ...mcq, result: res })
    }catch(e:any){ setMcqError(e.message) }
  }

  // Flashcards
  const [fc, setFc] = useState<any>(null)
  const [fcReveal, setFcReveal] = useState(false)
  const [fcStats, setFcStats] = useState<any>(null)
  const [fcLoading, setFcLoading] = useState(false)
  async function loadFcStats(){ try{ setFcStats(await apiGet(`/flashcards/stats?course_id=${encodeURIComponent(id)}`)) }catch{} }
  async function fcGenerate(){
    setFcLoading(true)
    await apiPost('/flashcards/generate', { course_id: id })
    await loadFcStats()
    setFcReveal(false)
    await fcNext()
    setFcLoading(false)
  }
  async function fcNext(){
    setFcLoading(true)
    const exclude = fc?.id ? `&exclude_id=${fc.id}` : ''
    const next = await apiGet(`/flashcards/next?course_id=${encodeURIComponent(id)}&reveal=true${exclude}`)
    setFcReveal(false)
    setFc(next)
    setFcLoading(false)
  }
  async function fcGrade(ok: boolean){
    if(!fc?.id) return
    await apiPost('/flashcards/grade', { course_id: id, flashcard_id: fc.id, correct: ok })
    await loadFcStats()
    setFcReveal(false)
    await fcNext()
  }

  // Deletes
  async function handleDeleteFile(name: string){
    await apiDelete(`/materials?course_id=${encodeURIComponent(id)}&name=${encodeURIComponent(name)}`)
    refetchFiles()
  }
  async function handleDeleteYouTube(url: string){
    await apiDelete(`/materials/youtube?course_id=${encodeURIComponent(id)}&url=${encodeURIComponent(url)}`)
    refetchYt()
  }

  // File item menu state (outside-click close)
  const [fileMenuOpen, setFileMenuOpen] = useState<string | null>(null)
  const fileMenuRefs = useRef<Record<string, HTMLDivElement | null>>({})
  useEffect(() => {
    function onClick(e: MouseEvent){
      if(!fileMenuOpen) return
      const ref = fileMenuRefs.current[fileMenuOpen]
      if(ref && !ref.contains(e.target as Node)) setFileMenuOpen(null)
    }
    window.addEventListener('click', onClick)
    return () => window.removeEventListener('click', onClick)
  }, [fileMenuOpen])

  // YouTube item menu and inline player state
  const [ytMenuOpen, setYtMenuOpen] = useState<string | null>(null) // key by url
  const ytMenuRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [playingUrl, setPlayingUrl] = useState<string | null>(null)
  useEffect(() => {
    function onClick(e: MouseEvent){
      if(!ytMenuOpen) return
      const ref = ytMenuRefs.current[ytMenuOpen]
      if(ref && !ref.contains(e.target as Node)) setYtMenuOpen(null)
    }
    window.addEventListener('click', onClick)
    return () => window.removeEventListener('click', onClick)
  }, [ytMenuOpen])

  function youtubeEmbedUrl(url: string, videoId?: string){
    const idFromParam = (() => {
      try{
        const u = new URL(url)
        if(u.hostname === 'youtu.be') return u.pathname.slice(1)
        const v = u.searchParams.get('v')
        return v || ''
      }catch{ return '' }
    })()
    const id = (videoId || idFromParam || '').trim()
    return id ? `https://www.youtube.com/embed/${id}` : ''
  }

  return (
    <div className="container py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/courses" aria-label="Back to courses" className="btn btn-outline px-3 py-1">←</Link>
          <h1 className="text-2xl font-semibold">{id}</h1>
        </div>
        <div className="relative" ref={headerMenuRef}>
          <button className="px-2 py-1 rounded hover:bg-white/10" onClick={()=>setMenuOpen(v=>!v)} aria-label="Open menu">⋯</button>
          {menuOpen && (
            <div className="absolute right-0 mt-2 w-44 bg-card border border-white/10 rounded-lg shadow-lg z-10">
              <button className="w-full text-left px-3 py-2 hover:bg-white/10" onClick={()=>{navigator.clipboard?.writeText(window.location.href); setMenuOpen(false); push({ message: 'Link copied', kind: 'success' })}}>Share link</button>
              <button className="w-full text-left px-3 py-2 text-red-400 hover:bg-white/10" onClick={async()=>{const ok=confirm('Delete course?'); if(!ok) return; await apiDelete(`/courses/${encodeURIComponent(id)}`); router.push('/courses')}}>Delete course</button>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
  <div className="flex gap-2 border-b border-white/10">
        {tabs.map(t => {
          const count = t.key === 'materials' ? ((files?.items || []).length) : t.key === 'youtube' ? ((yt?.items || []).length) : null
          return (
    <button key={t.key} className={`course-tab ${tab===t.key ? 'active' : ''}`} onClick={()=>setTab(t.key)}>
              {t.label}
              {typeof count === 'number' && count > 0 && (
        <span className="tab-count ml-2 text-xs bg-white/10 rounded-full px-2 py-0.5">{count}</span>
              )}
            </button>
          )
        })}
      </div>

      {/* Summary Panel */}
      {tab === 'summary' && (
        <div className="card p-4">
          <div className="flex gap-3 mb-3">
            <button className="btn btn-primary" onClick={runSummarize} disabled={sumLoading}>{sumLoading ? 'Summarizing…' : 'Summarize'}</button>
          </div>
          {summary ? (<pre className="whitespace-pre-wrap text-sm">{summary}</pre>) : (<div className="text-muted text-sm">No summary yet. Click Summarize.</div>)}
        </div>
      )}

      {/* MCQ Panel */}
      {tab === 'mcq' && (
        <div className="card p-4 space-y-3">
          <div className="flex gap-2 items-center">
            <button className="btn btn-primary" onClick={mcqNext} disabled={mcqLoading}>{mcqLoading ? (<><Spinner size={16} /> <span className="ml-2">Generating…</span></>) : 'Next Question'}</button>
          </div>
          {mcqError && <div className="text-red-400 text-sm">{mcqError}</div>}
          {mcq && (
            <div className="space-y-2">
              <div className="font-medium">{mcq.question}</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {mcq.options?.map((o:string, i:number) => (
                  <button key={i} className="btn btn-outline" onClick={()=>mcqAnswer(i)}>{o}</button>
                ))}
              </div>
              {mcq.result && (
                <div className="pt-2">
                  <div className={mcq.result.correct ? 'text-green-400' : 'text-red-400'}>
                    {mcq.result.correct ? 'Correct!' : 'Incorrect'}
                  </div>
                  <div className="text-sm text-muted">Answer: {mcq.options?.[mcq.result.answer_index]}</div>
                  <div className="text-sm">Explanation: {mcq.result.explanation}</div>
                </div>
              )}
            </div>
          )}
          {!mcq && !mcqError && <div className="text-sm text-muted">Click Next Question to start.</div>}
        </div>
      )}

      {/* Flashcards Panel */}
      {tab === 'flashcards' && (
        <div className="space-y-4">
          <div className="card p-4 flex gap-2 items-center">
            <button className="btn btn-primary" onClick={fcNext} disabled={fcLoading}>{fcLoading ? (<><Spinner size={16} /> <span className="ml-2">Loading…</span></>) : 'Next'}</button>
            <button className="btn btn-outline" onClick={fcGenerate} disabled={fcLoading}>{fcLoading ? (<><Spinner size={16} /> <span className="ml-2">Generating…</span></>) : 'Generate'}</button>
            <button className="btn btn-outline" onClick={loadFcStats}>Refresh Stats</button>
            <Link className="btn btn-outline ml-auto" href={`/courses/${encodeURIComponent(id)}/flashcards`}>View All</Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <div className="card p-0 min-h-[200px] overflow-hidden">
                {!fc && <div className="p-6 text-muted">No card loaded. Click Next.</div>}
                {fc && fc.status === 'empty' && <div className="p-6 text-muted">No flashcards yet. Click Generate.</div>}
                {fc && fc.status === 'ok' && (
                  <FlipCard
                    flipped={fcReveal}
                    onToggle={()=>setFcReveal(v=>!v)}
                    front={<div className="p-6 min-h-[200px] flex items-center justify-center text-center"><div className="font-semibold">{fc.question}</div></div>}
                    back={<div className="p-6 min-h-[200px] flex items-center justify-center text-center"><div className="text-sm">{fc.answer}</div></div>}
                  />
                )}
              </div>
              {fc && fc.status === 'ok' && (
                <div className="flex gap-2 pt-3">
                  <button className="btn btn-outline" onClick={()=>fcGrade(false)} disabled={fcLoading}>Incorrect</button>
                  <button className="btn btn-primary" onClick={()=>fcGrade(true)} disabled={fcLoading}>Correct</button>
                </div>
              )}
            </div>
            <div>
              <div className="card p-4">
                <div className="font-medium mb-2">Stats</div>
                {!fcStats && <div className="text-muted text-sm">No data</div>}
                {fcStats && (
                  <div className="space-y-1 text-sm">
                    <div>Due now: <span className="font-semibold">{fcStats.due ?? 0}</span></div>
                    <div className="grid grid-cols-5 gap-2">
                      {[1,2,3,4,5].map(i => (
                        <div key={i} className="text-center p-2 bg-white/5 rounded">
                          <div className="text-xs text-muted">Box {i}</div>
                          <div className="font-semibold">{(fcStats.counts||{})[i] ?? 0}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Materials Panel */}
      {tab === 'materials' && (
        <section>
          <div className="card p-4 space-y-4">
            {/* Inline upload */}
            <InlineUpload courseId={id} onUploaded={() => refetchFiles()} />
            <hr className="border-white/10" />
            {(files?.items||[]).length === 0 && <p className="text-muted">No files uploaded.</p>}
            {(files?.items||[]).map((f:any) => (
              <div key={f.name} className="flex items-center justify-between gap-4">
                <span>{f.name}</span>
                <div className="relative" ref={(el: HTMLDivElement | null) => { fileMenuRefs.current[f.name] = el }}>
                  <button className="px-2 py-1 rounded hover:bg-white/10" aria-label="file menu" onClick={(e: React.MouseEvent<HTMLButtonElement>)=>{
                    e.preventDefault(); e.stopPropagation(); setFileMenuOpen(v => v === f.name ? null : f.name)
                  }}>⋯</button>
                  {fileMenuOpen === f.name && (
                    <div className="absolute right-0 mt-2 w-36 bg-card border border-white/10 rounded-lg shadow-lg z-10">
                      <a className="block px-3 py-2 hover:bg-white/10" href={`${API_BASE}/materials/download?course_id=${encodeURIComponent(id)}&name=${encodeURIComponent(f.name)}`} target="_blank">Download</a>
                      <button className="w-full text-left px-3 py-2 text-red-400 hover:bg-white/10" onClick={()=>{ handleDeleteFile(f.name); setFileMenuOpen(null) }}>Delete</button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Chat (RAG) Panel */}
      {tab === 'chat' && (
        <section>
          <CourseChat courseId={id} />
        </section>
      )}

      {/* YouTube Panel */}
      {tab === 'youtube' && (
        <section>
          <div className="space-y-4">
            <InlineYouTubeIngest courseId={id} onIngested={() => refetchYt()} />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {(yt?.items||[]).length === 0 && <p className="text-muted">No YouTube videos.</p>}
            {(yt?.items||[]).map((v:any) => (
              <div key={v.url} className="card p-2">
                <a href={v.url} target="_blank">
                  {v.thumbnail_url && (
                    <Image src={v.thumbnail_url} alt="thumbnail" width={480} height={270} className="w-full h-auto rounded-lg" />
                  )}
                  <div className="px-2 py-2 text-sm text-muted">Open on YouTube</div>
                </a>
                <div className="flex justify-end px-2 pb-2">
                  <div className="relative" ref={(el: HTMLDivElement | null) => { ytMenuRefs.current[v.url] = el }}>
                    <button className="px-2 py-1 rounded hover:bg-white/10" onClick={(e: React.MouseEvent<HTMLButtonElement>)=>{ e.preventDefault(); e.stopPropagation(); setYtMenuOpen(k => k === v.url ? null : v.url) }} aria-label="video menu">⋯</button>
                    {ytMenuOpen === v.url && (
                      <div className="absolute right-0 mt-2 w-44 bg-card border border-white/10 rounded-lg shadow-lg z-10">
                        <a className="block px-3 py-2 hover:bg-white/10" href={v.url} target="_blank">Open</a>
                        <button className="w-full text-left px-3 py-2 hover:bg-white/10" onClick={()=>{ setPlayingUrl(p => p === v.url ? null : v.url); setYtMenuOpen(null) }}>
                          {playingUrl === v.url ? 'Hide inline' : 'Play inline'}
                        </button>
                        <button className="w-full text-left px-3 py-2 text-red-400 hover:bg-white/10" onClick={()=>{ handleDeleteYouTube(v.url); setYtMenuOpen(null); if(playingUrl===v.url) setPlayingUrl(null); push({ message: 'Removed', kind: 'success' }) }}>Remove</button>
                      </div>
                    )}
                  </div>
                </div>
                {playingUrl === v.url && (
                  <div className="mt-2 w-full rounded-lg overflow-hidden" style={{ position: 'relative', paddingTop: '56.25%' }}>
                    <iframe
                      src={youtubeEmbedUrl(v.url, v.video_id)}
                      title="YouTube video player"
                      frameBorder="0"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                      allowFullScreen
                      style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
                    />
                  </div>
                )}
              </div>
            ))}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

function CourseChat({ courseId }: { courseId: string }){
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<{ id?: number; q: string; a: string; t: string | number; open?: boolean }[]>([])
  const [visible, setVisible] = useState(10)

  // Load from backend and reset UI state on mount
  async function fetchHistory(resetVisible = true){
    try{
      const res = await fetch(`${API_BASE}/chat/history?course_id=${encodeURIComponent(courseId)}&limit=100&offset=0`).then(r=>r.json())
      const items = (res.items||[]).map((m:any, idx:number) => ({ ...m, open: idx === 0 }))
      setHistory(items)
      if(resetVisible) setVisible(10)
    }catch{}
  }
  useEffect(() => {
    setInput('')
    fetchHistory(true)
  }, [courseId])

  async function ask(){
    if(!input.trim()) return
    setLoading(true)
    try{
      const res = await apiPost<any>('/rag/chat', { query: input, course_id: courseId, include_summary: true })
  // Prepend and auto-open the latest answer
  setHistory(h => [{ q: input, a: res?.answer || '', t: new Date().toISOString(), open: true }, ...h.map(i => ({...i, open: false}))])
      setInput('')
  // Sync with server to get persisted IDs and canonical order
  fetchHistory(false)
    }catch(e:any){
  setHistory(h => [{ q: input, a: `Error: ${e.message||e}`, t: new Date().toISOString(), open: true }, ...h.map(i => ({...i, open: false}))])
    }finally{ setLoading(false) }
  }
  async function removeItem(itemId: number){
    try{
      await apiDelete(`/chat/history?course_id=${encodeURIComponent(courseId)}&id=${itemId}`)
      // Update local state quickly without full refetch
      setHistory(list => list.filter(it => it.id !== itemId))
    }catch{}
  }
  return (
    <div className="card p-4 space-y-4">
      {/* Ask at top */}
      <form className="flex gap-2" onSubmit={(e)=>{ e.preventDefault(); ask() }}>
        <input className="bg-card border border-white/20 rounded px-3 py-2 flex-1" placeholder="Ask anything about this course" value={input} onChange={e=>setInput(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={loading}>{loading ? (<><Spinner size={16} /> <span className="ml-2">Thinking…</span></>) : 'Ask'}</button>
      </form>

      {/* History as dropdown/accordion */}
      <div className="space-y-2 max-h-[460px] overflow-auto pr-1">
  {history.slice(0, visible).map((h,i) => {
          const key = `${h.t}-${i}`
          return (
            <details key={key} className="bg-white/5 rounded-lg" open={!!h.open} onClick={(e)=>{
              // toggle open state manually so only one is open if user interacts
              e.preventDefault()
              setHistory(list => list.map((it, idx) => idx === i ? ({...it, open: !it.open}) : it))
            }}>
              <summary className="list-none cursor-pointer px-3 py-2 hover:bg-white/10 rounded-lg">
                <div className="text-sm font-medium truncate">{h.q}</div>
              </summary>
              <div className="px-3 pb-3 pt-1 relative">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs text-muted">Answer</div>
                  <div className="flex items-center gap-2">
                    <button
                      className="text-[11px] px-2 py-1 rounded bg-white/10 hover:bg-white/20"
                      onClick={async (e)=>{ e.preventDefault(); e.stopPropagation(); try{ await navigator.clipboard.writeText(h.a||'') }catch{} }}
                      title="Copy answer"
                    >Copy</button>
                    {!!h.id && (
                      <button
                        className="text-[11px] px-2 py-1 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300"
                        onClick={async (e)=>{ e.preventDefault(); e.stopPropagation(); const ok=confirm('Delete this chat?'); if(!ok) return; await removeItem(h.id as number); }}
                        title="Delete chat"
                      >Delete</button>
                    )}
                  </div>
                </div>
                <div className="whitespace-pre-wrap text-sm">{h.a}</div>
              </div>
            </details>
          )
        })}
        {!history.length && <div className="text-muted text-sm">Ask a question to get started.</div>}
        {history.length > visible && (
          <div className="flex justify-center pt-2">
            <button className="btn btn-outline" onClick={()=>setVisible(v=>v+10)}>Load More</button>
          </div>
        )}
      </div>
    </div>
  )
}

// Inline components for uploading files and ingesting YouTube
function InlineUpload({ courseId, onUploaded }: { courseId: string; onUploaded: () => void }){
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  async function onSubmit(e: React.FormEvent){
    e.preventDefault()
    if(!files.length) return
    setUploading(true)
    try{
      // Upload each file separately as the backend expects a single 'file'
      for(const file of files){
        const form = new FormData()
        form.append('file', file)
        form.append('course_id', courseId)
        const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form })
        if(!res.ok) throw new Error(await res.text())
      }
      onUploaded()
      setFiles([])
    }catch(err){ console.error(err) }
    finally{ setUploading(false) }
  }
  return (
    <form onSubmit={onSubmit} className="flex items-center gap-3">
      <input
        type="file"
        multiple
        className="bg-card border border-white/20 rounded px-3 py-2"
        onChange={e=>setFiles(Array.from(e.target.files||[]))}
      />
      <button className="btn btn-primary" disabled={!files.length || uploading}>
        {uploading ? `Uploading…` : (files.length ? `Upload ${files.length} file${files.length>1?'s':''}` : 'Upload')}
      </button>
    </form>
  )
}

function InlineYouTubeIngest({ courseId, onIngested }: { courseId: string; onIngested: () => void }){
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  async function onSubmit(e: React.FormEvent){
    e.preventDefault()
    if(!url.trim()) return
    setLoading(true)
    try{
      const res = await fetch(`${API_BASE}/ingest/youtube`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, course_id: courseId })
      })
      if(!res.ok) throw new Error(await res.text())
      onIngested()
      setUrl('')
    }catch(err){ console.error(err) }
    finally{ setLoading(false) }
  }
  return (
    <form onSubmit={onSubmit} className="card p-3 flex items-center gap-2">
      <input className="bg-card border border-white/20 rounded px-3 py-2 flex-1" placeholder="Paste YouTube URL" value={url} onChange={e=>setUrl(e.target.value)} />
      <button className="btn btn-primary" disabled={!url.trim() || loading}>{loading ? 'Adding…' : 'Add Video'}</button>
    </form>
  )
}
