'use client'

import { useState } from 'react'
import { useStandings } from '@/hooks/useStandings'
import { StandingsTabs } from './StandingsTabs'
import { StandingsRow } from './StandingsRow'

export function StandingsPanel() {
  const [tab, setTab] = useState<'drivers' | 'constructors'>('drivers')
  const { drivers, constructors, loading, error } = useStandings()

  return (
    <div className="w-[280px] flex-shrink-0 flex flex-col" style={{ background: '#0d0d0d' }}>
      {/* Header */}
      <div className="px-5 pt-4 pb-3 border-b" style={{ borderColor: 'var(--f1-border)' }}>
        <p className="text-[11px] font-bold tracking-widest uppercase" style={{ color: 'var(--f1-red)' }}>
          2025 Season
        </p>
        <p className="text-[11px]" style={{ color: 'var(--f1-muted)' }}>Live standings</p>
      </div>

      <StandingsTabs active={tab} onChange={setTab} />

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="px-5 py-4 text-[12px]" style={{ color: 'var(--f1-muted)' }}>
            Loading standings...
          </div>
        )}
        {error && (
          <div className="px-5 py-4 text-[12px]" style={{ color: 'var(--f1-muted)' }}>
            Standings unavailable
          </div>
        )}
        {!loading && !error && tab === 'drivers' &&
          drivers.map(d => (
            <StandingsRow
              key={d.position}
              position={d.position}
              name={d.driver}
              team={d.team}
              points={d.points}
            />
          ))
        }
        {!loading && !error && tab === 'constructors' &&
          constructors.map(c => (
            <StandingsRow
              key={c.position}
              position={c.position}
              name={c.team}
              points={c.points}
            />
          ))
        }
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t text-[11px]" style={{ borderColor: 'var(--f1-border)', color: '#444' }}>
        Updated via Jolpica · Refreshes every 6h
      </div>
    </div>
  )
}
