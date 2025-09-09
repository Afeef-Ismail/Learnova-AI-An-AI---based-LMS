"use client";

import type { ReactNode } from 'react'

export function FlipCard({ front, back, flipped = false, onToggle }: { front: ReactNode; back: ReactNode; flipped?: boolean; onToggle?: () => void }){
  return (
    <div className="flip-card" onClick={onToggle}>
      <div className={`flip-inner ${flipped ? 'flipped' : ''}`}>
        <div className="flip-front">
          {front}
        </div>
        <div className="flip-back">
          {back}
        </div>
      </div>
    </div>
  )
}
