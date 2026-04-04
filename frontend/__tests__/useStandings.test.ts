import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useStandings } from '@/hooks/useStandings'
import * as api from '@/lib/api'

vi.mock('@/lib/api')

const mockDrivers = [
  { position: 1, driver: 'Max Verstappen', team: 'Red Bull Racing', points: 136 },
  { position: 2, driver: 'Lando Norris', team: 'McLaren', points: 113 },
]
const mockConstructors = [
  { position: 1, team: 'Red Bull Racing', points: 249 },
  { position: 2, team: 'McLaren', points: 174 },
]

describe('useStandings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.fetchDriverStandings).mockResolvedValue(mockDrivers)
    vi.mocked(api.fetchConstructorStandings).mockResolvedValue(mockConstructors)
  })

  it('fetches driver and constructor standings on mount', async () => {
    const { result } = renderHook(() => useStandings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.drivers).toHaveLength(2)
    expect(result.current.constructors).toHaveLength(2)
    expect(result.current.drivers[0].driver).toBe('Max Verstappen')
  })

  it('sets error when fetch fails', async () => {
    vi.mocked(api.fetchDriverStandings).mockRejectedValue(new Error('Network error'))
    const { result } = renderHook(() => useStandings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
  })

  it('starts in loading state', () => {
    const { result } = renderHook(() => useStandings())
    expect(result.current.loading).toBe(true)
  })
})
