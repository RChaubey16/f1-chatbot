import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChat } from '@/hooks/useChat'
import * as api from '@/lib/api'

vi.mock('@/lib/api')

describe('useChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts with empty messages', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.messages).toHaveLength(0)
  })

  it('appends user message immediately on send', async () => {
    vi.mocked(api.streamChat).mockImplementation(async (_q, _onToken, onDone) => {
      onDone()
    })
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await result.current.sendMessage('Who won 2023?')
    })
    expect(result.current.messages[0].role).toBe('user')
    expect(result.current.messages[0].content).toBe('Who won 2023?')
  })

  it('appends AI message with streamed tokens', async () => {
    vi.mocked(api.streamChat).mockImplementation(async (_q, onToken, onDone) => {
      onToken('Max ')
      onToken('won.')
      onDone()
    })
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await result.current.sendMessage('Who won 2023?')
    })
    const aiMsg = result.current.messages.find(m => m.role === 'ai')
    expect(aiMsg?.content).toBe('Max won.')
  })

  it('sets streaming=false after stream completes', async () => {
    vi.mocked(api.streamChat).mockImplementation(async (_q, _onToken, onDone) => {
      onDone()
    })
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await result.current.sendMessage('test')
    })
    expect(result.current.isStreaming).toBe(false)
  })

  it('falls back to sendChat on stream error', async () => {
    vi.mocked(api.streamChat).mockRejectedValue(new Error('SSE failed'))
    vi.mocked(api.sendChat).mockResolvedValue({
      answer: 'Fallback answer',
      sources: [],
      intent: 'HISTORICAL',
      latency_ms: 99,
    })
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await result.current.sendMessage('test')
    })
    const aiMsg = result.current.messages.find(m => m.role === 'ai')
    expect(aiMsg?.content).toBe('Fallback answer')
  })
})
