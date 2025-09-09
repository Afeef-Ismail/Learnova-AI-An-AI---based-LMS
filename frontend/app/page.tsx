"use client";
import { useEffect, useState } from 'react'

export default function Home() {
  const [name, setName] = useState<string>('Learner')
  useEffect(() => {
    try{
      const t = typeof window !== 'undefined' ? localStorage.getItem('jwt') : null
      if (t){
        const [, payload] = t.split('.')
        const json = JSON.parse(atob(payload.replace(/-/g,'+').replace(/_/g,'/')))
        if (json?.name) setName(json.name)
      }
    }catch{}
  }, [])

  return (
    <div className="container py-8 space-y-8">
      <header className="card p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Welcome back, {name}!</h1>
            <p className="text-muted mt-1">Keep learning, you're doing great!</p>
          </div>
          <form className="hidden md:flex items-center bg-white/5 rounded-lg px-3 py-2 w-[420px]">
            <input className="bg-transparent outline-none flex-1" placeholder="Search for courses, topics, or instructors..." />
          </form>
        </div>
      </header>

      <section>
        <h2 className="text-xl font-semibold mb-3">My Learning</h2>
        <div className="card p-6">
          <p className="text-lg font-medium">Your learning journey starts here!</p>
          <p className="text-muted">Upload your first learning material to begin.</p>
          <a href="/upload" className="btn btn-primary mt-4 inline-block w-max">Upload New Material</a>
        </div>
      </section>
    </div>
  )
}
