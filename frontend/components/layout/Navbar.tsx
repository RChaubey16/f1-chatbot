'use client'

import { useEffect, useState } from 'react'
import { checkHealth } from '@/lib/api'

export function Navbar() {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    checkHealth().then(setOnline)
  }, [])

  return (
    <nav
      className="flex items-center justify-between px-6 flex-shrink-0"
      style={{
        height: '52px',
        background: 'var(--f1-surface)',
        borderBottom: '2px solid var(--f1-red)',
      }}
    >
      <div className="flex items-center gap-2.5 font-bold text-base tracking-wide">
        <span
          className="text-[11px] font-black px-1.5 py-0.5 rounded text-white"
          style={{ background: 'var(--f1-red)', letterSpacing: '0.1em' }}
        >
          F1
        </span>
        <span style={{ color: 'var(--f1-text)' }}>Chatbot</span>
      </div>

      <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--f1-muted)' }}>
        {online !== null && (
          <>
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: online ? '#22c55e' : '#ef4444' }}
            />
            {online ? 'API Connected' : 'API Offline'}
          </>
        )}
      </div>
    </nav>
  )
}
