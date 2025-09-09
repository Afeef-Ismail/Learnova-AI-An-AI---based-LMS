"use client";
import { useEffect, useState } from 'react'

export default function ProfilePage(){
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  useEffect(() => {
    try{
      const t = localStorage.getItem('jwt')
      if (!t) return
      const [, payload] = t.split('.')
      const json = JSON.parse(atob(payload.replace(/-/g,'+').replace(/_/g,'/')))
      setName(json?.name || '')
      setEmail(json?.email || '')
    }catch{}
  }, [])

  return (
    <div className="container py-8 space-y-6">
      <h1 className="text-2xl font-semibold">Profile</h1>
      <div className="card p-4 space-y-2">
        <div><span className="text-muted">Name:</span> {name || '—'}</div>
        <div><span className="text-muted">Email:</span> {email || '—'}</div>
      </div>
    </div>
  )
}
