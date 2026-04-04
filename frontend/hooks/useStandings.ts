'use client'

import { useState, useEffect, useCallback } from 'react'
import { fetchDriverStandings, fetchConstructorStandings } from '@/lib/api'
import type { DriverStanding, ConstructorStanding } from '@/lib/types'

const SIX_HOURS_MS = 6 * 60 * 60 * 1000

export function useStandings() {
  const [drivers, setDrivers] = useState<DriverStanding[]>([])
  const [constructors, setConstructors] = useState<ConstructorStanding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [d, c] = await Promise.all([
        fetchDriverStandings(),
        fetchConstructorStandings(),
      ])
      setDrivers(d)
      setConstructors(c)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, SIX_HOURS_MS)
    return () => clearInterval(interval)
  }, [])

  return { drivers, constructors, loading, error }
}
