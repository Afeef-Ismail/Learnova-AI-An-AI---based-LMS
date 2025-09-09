"use client";

import { useState } from 'react'
import { API_BASE } from '../../lib/api'

export default function UploadPage(){
  const [courseName, setCourseName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<string>('')
  const [ytUrl, setYtUrl] = useState('')
  const [autoSum, setAutoSum] = useState(true)

  async function onSubmit(e: React.FormEvent){
    e.preventDefault()
  if(!file){ setStatus('Please choose a file'); return }
  if(!courseName.trim()){ setStatus('Please enter a course name'); return }
    const fd = new FormData()
  fd.append('course_id', courseName.trim())
    fd.append('file', file)
    setStatus('Uploading...')
    try{
  const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: fd })
      if(!res.ok){ throw new Error(await res.text()) }
      setStatus('Uploaded and ingested')
    }catch(err:any){ setStatus(err.message) }
  }

  return (
    <div className="container py-8">
      <h1 className="text-2xl font-semibold mb-4">Upload Material</h1>
      <form onSubmit={onSubmit} className="card p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm mb-1">Course name</label>
            <input value={courseName} onChange={e=>setCourseName(e.target.value)} placeholder="e.g., Algebra 101" className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none" />
          </div>
          <div>
            <label className="block text-sm mb-1">File</label>
            <input type="file" onChange={e=>setFile(e.target.files?.[0] || null)} className="w-full" />
          </div>
        </div>
        <button type="submit" className="btn btn-primary">Upload</button>
        {status && <p className="text-sm text-muted">{status}</p>}
      </form>

      <div className="card p-6 space-y-4 mt-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-1">
            <label className="block text-sm mb-1">YouTube URL</label>
            <input value={ytUrl} onChange={e=>setYtUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none" />
          </div>
          <div>
            <label className="block text-sm mb-1">Course name</label>
            <input value={courseName} onChange={e=>setCourseName(e.target.value)} placeholder="e.g., Algebra 101" className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 outline-none" />
          </div>
          <div className="flex items-end">
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={autoSum} onChange={e=>setAutoSum(e.target.checked)} />
              <span>Auto-summarize after ingest</span>
            </label>
          </div>
        </div>
        <button className="btn btn-primary w-max" onClick={async()=>{
          if(!ytUrl.trim()){ setStatus('Enter a YouTube URL'); return }
      if(!courseName.trim()){ setStatus('Please enter a course name'); return }
          setStatus('Ingesting YouTube...')
          try{
            const res = await fetch(`${API_BASE}/ingest/youtube`, {
              method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ url: ytUrl.trim(), course_id: courseName.trim(), summarize: autoSum })
            })
            if(!res.ok){ throw new Error(await res.text()) }
            setStatus('YouTube ingested successfully')
          }catch(err:any){ setStatus(err.message) }
        }}>Ingest YouTube</button>
      </div>
    </div>
  )
}
