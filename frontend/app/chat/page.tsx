"use client";

import { useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE } from '../../lib/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

type Msg = { role: 'user' | 'assistant'; content: string }
type Chat = { id: string; name: string; messages: Msg[] }

export default function ChatPage(){
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<Msg[]>([])
  const [chats, setChats] = useState<Chat[]>([])
  const [currentId, setCurrentId] = useState<string>('')
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [history])

  // Persist chats in localStorage
  useEffect(() => {
    try {
      const raw = localStorage.getItem('edu_chats')
      if(raw){
        const parsed: Chat[] = JSON.parse(raw)
        setChats(parsed)
        const cid = localStorage.getItem('edu_chats_current') || (parsed[0]?.id || '')
        setCurrentId(cid)
        const cur = parsed.find(c => c.id === cid)
        setHistory(cur?.messages || [])
      } else {
        const first: Chat = { id: String(Date.now()), name: 'New chat', messages: [] }
        setChats([first])
        setCurrentId(first.id)
        setHistory([])
        localStorage.setItem('edu_chats', JSON.stringify([first]))
        localStorage.setItem('edu_chats_current', first.id)
      }
    } catch {}
  }, [])
  useEffect(() => {
    // keep current chat in sync
    setChats(prev => prev.map(c => c.id === currentId ? { ...c, messages: history } : c))
  }, [history, currentId])
  useEffect(() => {
    // persist chats anytime it changes
    try {
      if(chats.length){
        localStorage.setItem('edu_chats', JSON.stringify(chats))
      }
      if(currentId){
        localStorage.setItem('edu_chats_current', currentId)
      }
    } catch {}
  }, [chats, currentId])

  function newConversation(){
    abortRef.current?.abort()
    const c: Chat = { id: String(Date.now()), name: 'New chat', messages: [] }
    setChats(prev => [c, ...prev])
    setCurrentId(c.id)
    setHistory([])
    setQuestion('')
    setEditingIndex(null)
    setTimeout(() => inputRef.current?.focus(), 0)
  }
  const [loading, setLoading] = useState(false)

  // Client no longer filters; server enforces policy

  async function streamFromMessages(messages: Msg[]){
    setLoading(true)
    // Abort any previous stream
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try{
      // Prime assistant placeholder with provided messages
      setHistory([...messages, { role: 'assistant', content: '' }])
      const res = await fetch(`${API_BASE}/chat/edu/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages }),
        signal: controller.signal,
      })
      if(!res.ok || !res.body){
        const res2 = await fetch(`${API_BASE}/chat/edu`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages }) })
        const data = await res2.json()
        const a = data.response || ''
        setHistory(h => { const hh=[...h]; for(let i=hh.length-1;i>=0;i--){ if(hh[i].role==='assistant'){ hh[i]={role:'assistant', content:a}; break } } return hh })
      } else {
        const reader = res.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let done = false
        while(!done){
          const { value, done: d } = await reader.read()
          done = d
          if(value){
            const chunk = decoder.decode(value, { stream: true })
            if(chunk){
              setHistory(h => {
                const hh = [...h]
                for(let i=hh.length-1;i>=0;i--){ if(hh[i].role==='assistant'){ hh[i]={role:'assistant', content:(hh[i].content||'')+chunk}; break } }
                return hh
              })
            }
          }
        }
      }
    } catch(err:any){
      const a = (err?.name === 'AbortError') ? '' : (err?.message || 'Error')
      if(a){ setHistory(h=>{ const hh=[...h]; for(let i=hh.length-1;i>=0;i--){ if(hh[i].role==='assistant'){ hh[i]={role:'assistant', content:(hh[i].content||'')+a}; break } } return hh }) }
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }

  async function ask(){
    const q = question.trim()
    if(!q) return
    // Clear the input immediately after submit
    setQuestion('')
    setEditingIndex(null)
    // Build messages for multi-turn context with correct types
    let newMessages: Msg[]
    if (editingIndex !== null) {
      const tmp: Msg[] = history.map((m, i): Msg => (i === editingIndex ? { role: 'user', content: q } : m))
      newMessages = tmp.filter((_, i) => !(i === (editingIndex as number) + 1 && tmp[i]?.role === 'assistant'))
    } else {
      newMessages = [...history, { role: 'user', content: q }]
    }
    await streamFromMessages(newMessages)
  }

  function stop(){
    abortRef.current?.abort()
  }

  function renameCurrent(){
    const cur = chats.find(c => c.id === currentId)
    if(!cur) return
    const nn = window.prompt('Rename chat', cur.name) || cur.name
    setChats(prev => prev.map(c => c.id === currentId ? { ...c, name: nn } : c))
  }

  function switchChat(id: string){
    if(id === currentId) return
    abortRef.current?.abort()
    setCurrentId(id)
    const cur = chats.find(c => c.id === id)
    setHistory(cur?.messages || [])
    setQuestion('')
    setEditingIndex(null)
  }

  // Utilities for actions on last turns
  const lastUserIndex = useMemo(() => {
    for(let i=history.length-1;i>=0;i--){ if(history[i].role==='user') return i }
    return -1
  }, [history])
  const lastAssistantIndex = useMemo(() => {
    for(let i=history.length-1;i>=0;i--){ if(history[i].role==='assistant') return i }
    return -1
  }, [history])

  async function regenerate(){
    if(lastUserIndex < 0) return
    const messages: Msg[] = history.filter((_, i) => i !== lastAssistantIndex)
    await streamFromMessages(messages)
  }

  async function continueAnswer(){
    const messages: Msg[] = [...history, { role: 'user', content: 'Continue.' }]
    await streamFromMessages(messages)
  }

  function onEditLast(){
    if(lastUserIndex < 0) return
    setEditingIndex(lastUserIndex)
    setQuestion(history[lastUserIndex].content)
    inputRef.current?.focus()
  }

  function renderMessage(m: Msg, i: number){
    const isAssistant = m.role === 'assistant'
    const bubbleBase = 'inline-block max-w-[80%] px-3 py-2 rounded-lg '
    const bubbleCls = isAssistant ? 'bg-white/5 border border-white/10' : 'bg-violet-600/20 border border-violet-400/30'
    return (
      <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
        <div className={`${bubbleBase}${bubbleCls}`}>
          <div className="text-xs text-muted mb-1">{m.role === 'user' ? 'You' : 'Assistant'}</div>
          {isAssistant ? (
            <div className="prose prose-invert prose-sm max-w-none relative">
              <button
                className="absolute -top-8 right-0 text-[11px] px-2 py-1 rounded bg-white/10 hover:bg-white/20"
                onClick={async ()=>{ try{ await navigator.clipboard.writeText(m.content) }catch{} }}
                title="Copy answer"
              >Copy answer</button>
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  code({node, inline, className, children, ...props}: any){
                    const text = String(children || '')
                    if(inline){
                      return <code className={className} {...props}>{text}</code>
                    }
                    const onCopy = async () => {
                      try { await navigator.clipboard.writeText(text) } catch {}
                    }
                    return (
                      <div className="relative group">
                        <button onClick={onCopy} className="absolute top-1 right-1 text-[11px] px-2 py-1 rounded bg-white/10 hover:bg-white/20">Copy</button>
                        <pre className={className}><code>{text}</code></pre>
                      </div>
                    )
                  }
                }}
              >
                {m.content}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="whitespace-pre-wrap text-sm">{m.content}</div>
          )}
          {(i === lastUserIndex && !isAssistant) && (
            <div className="mt-2 text-[12px] text-muted flex gap-3 justify-end">
              <button className="hover:underline" onClick={onEditLast}>Edit</button>
            </div>
          )}
          {(i === lastAssistantIndex && isAssistant) && (
            <div className="mt-2 text-[12px] text-muted flex gap-3">
              <button className="hover:underline" onClick={regenerate}>Regenerate</button>
              <button className="hover:underline" onClick={continueAnswer}>Continue</button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="container py-6 h-[calc(100vh-48px)] flex flex-col">
      <div className="px-1 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Educational Chatbot</h1>
            <p className="text-sm text-muted">Education, general knowledge, mathematics, and technology are in scope.</p>
          </div>
          <div className="flex items-center gap-2">
            <select className="bg-card border border-white/20 rounded px-2 py-1 text-sm" value={currentId} onChange={e=>switchChat(e.target.value)}>
              {chats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <button className="btn btn-outline" onClick={renameCurrent} disabled={!currentId}>Rename</button>
            <button className="btn bg-red-600 text-white hover:bg-red-500" onClick={() => {
              abortRef.current?.abort()
              setChats(prev => {
                const filtered = prev.filter(c => c.id !== currentId)
                if(filtered.length === 0){
                  const nc: Chat = { id: String(Date.now()), name: 'New chat', messages: [] }
                  setCurrentId(nc.id)
                  setHistory([])
                  return [nc]
                }
                const next = filtered[0]
                setCurrentId(next.id)
                setHistory(next.messages)
                return filtered
              })
            }} disabled={!currentId}>Delete</button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {loading ? (
            <button className="btn btn-warning" onClick={stop}>Stop</button>
          ) : null}
          <button className="btn btn-outline" onClick={newConversation} disabled={loading}>New conversation</button>
        </div>
      </div>
      <div className="flex-1 card p-0 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-auto px-4 py-4 space-y-3">
          {history.length === 0 && (
            <div className="text-sm text-muted">Ask a question to start the conversation.</div>
          )}
          {history.map((m, i) => renderMessage(m, i))}
          {loading && (
            <div className="text-left">
              <div className="inline-block max-w-[80%] px-3 py-2 rounded-lg bg-white/5 border border-white/10">
                <div className="text-xs text-muted mb-1">Assistant</div>
                <div className="text-sm"><span className="animate-pulse">Typing…</span></div>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
        <form className="border-t border-white/10 p-3 flex gap-2" onSubmit={(e)=>{ e.preventDefault(); if(!loading) ask() }}>
          <input ref={inputRef} className="bg-card border border-white/20 rounded px-3 py-2 flex-1" placeholder="Ask any subject question or math problem" value={question} onChange={e=>setQuestion(e.target.value)} />
          {loading ? (
            <button type="button" className="btn btn-warning" onClick={stop}>Stop</button>
          ) : (
            <button type="submit" className="btn btn-primary" disabled={loading}>Send</button>
          )}
        </form>
      </div>
    </div>
  )
}
