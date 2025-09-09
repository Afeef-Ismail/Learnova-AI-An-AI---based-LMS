"use client";
import { useEffect, useState } from 'react'
import { API_BASE } from '../../lib/api'

declare global { interface Window { google?: any } }

export default function LoginPage(){
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Load Google Identity script
    const id = 'google-identity'
    if (!document.getElementById(id)){
      const s = document.createElement('script')
      s.id = id
      s.src = 'https://accounts.google.com/gsi/client'
      s.async = true
      s.defer = true
      document.body.appendChild(s)
      s.onload = initGoogle
    } else {
      initGoogle()
    }
  }, [])

  function initGoogle(){
    if (!window.google) return
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ''
    if(!clientId) return
    window.google.accounts.id.initialize({ client_id: clientId, callback: async (resp: any)=>{
      try {
        setLoading(true)
        const res = await fetch(`${API_BASE}/auth/google`, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify({ id_token: resp.credential }) })
        const data = await res.json()
        if(!res.ok) throw new Error(data.detail || 'Google sign-in failed')
        localStorage.setItem('jwt', data.token)
        window.location.href = '/'
      } catch (e:any){ setError(e.message) } finally { setLoading(false) }
    }})
    try{
      window.google.accounts.id.renderButton(document.getElementById('googleBtn'), { theme: 'filled_blue', size: 'large', shape: 'pill', text: 'signin_with' })
    }catch{}
  }

  async function onLogin(e: React.FormEvent){
    e.preventDefault()
    setError(null)
    try{
      setLoading(true)
      const res = await fetch(`${API_BASE}/auth/login`, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify({ email, password }) })
      const data = await res.json()
      if(!res.ok) throw new Error(data.detail || 'Login failed')
      localStorage.setItem('jwt', data.token)
      window.location.href = '/'
    }catch(e:any){ setError(e.message) } finally { setLoading(false) }
  }

  return (
    <div className="container py-10 max-w-md">
      <h1 className="text-2xl font-semibold mb-4">Sign in</h1>
      <form onSubmit={onLogin} className="space-y-3">
        <input className="w-full bg-card border border-white/20 rounded px-3 py-2" placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} />
        <input type="password" className="w-full bg-card border border-white/20 rounded px-3 py-2" placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)} />
        {error && <div className="text-red-400 text-sm">{error}</div>}
        <button type="submit" className="btn btn-primary w-full" disabled={loading}>{loading? 'Signing in…' : 'Sign in'}</button>
      </form>
      <div className="my-4 text-center text-sm text-muted">or</div>
      <div id="googleBtn" className="flex justify-center" />
      <div className="mt-4 text-sm">
        New here? <a className="text-blue-400 underline" href="/signup">Create an account</a>
      </div>
    </div>
  )
}
