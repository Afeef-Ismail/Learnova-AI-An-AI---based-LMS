"use client";

import { useState } from 'react'
import useSWR from 'swr'
import { API_BASE } from '../../lib/api'
import { apiPost } from '../../lib/api'

const fetcher = (url: string) => fetch(url).then(r => r.json())

export default function MCQPage(){
  const [courseId, setCourseId] = useState('')
  const [current, setCurrent] = useState<any>(null)

  async function next(){
    if(!courseId) return
    const q = await apiPost<any>('/mcq/next', { course_id: courseId })
    setCurrent(q)
  }
  async function answer(idx: number){
    if(!current) return
    const res = await apiPost<any>('/mcq/answer', { course_id: courseId, question_id: current.id, selected_index: idx })
    setCurrent({ ...current, result: res })
  }

  return (
    <div className="container py-8 space-y-4">
      <h1 className="text-2xl font-semibold">MCQ Practice</h1>
      <div className="card p-4 flex gap-2 items-center">
        <input className="bg-card border border-white/20 rounded px-3 py-2 flex-1" placeholder="Enter course id" value={courseId} onChange={e => setCourseId(e.target.value)} />
        <button className="btn btn-primary" onClick={next}>Next Question</button>
      </div>

      {current && (
        <div className="card p-4 space-y-3">
          <div className="font-medium">{current.question}</div>
          <div className="grid grid-cols-1 gap-2">
            {current.options?.map((o: string, i: number) => (
              <button key={i} className="btn btn-outline" onClick={() => answer(i)}>{o}</button>
            ))}
          </div>
          {current.result && (
            <div className="mt-2">
              <div className={current.result.correct ? 'text-green-400' : 'text-red-400'}>
                {current.result.correct ? 'Correct!' : 'Incorrect'}
              </div>
              <div className="text-sm text-muted mt-1">Answer: {current.options?.[current.result.answer_index]}</div>
              <div className="text-sm mt-1">Explanation: {current.result.explanation}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
