'use client'

import { useState, useCallback } from 'react'
import { streamChat, sendChat } from '@/lib/api'
import type { Message, Source } from '@/lib/types'

function makeId() {
  return Math.random().toString(36).slice(2)
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)

  const sendMessage = useCallback(async (query: string) => {
    const userMsg: Message = { id: makeId(), role: 'user', content: query }
    const aiId = makeId()
    const aiMsg: Message = { id: aiId, role: 'ai', content: '', streaming: true }

    setMessages(prev => [...prev, userMsg, aiMsg])
    setIsStreaming(true)

    try {
      await streamChat(
        query,
        (token) => {
          setMessages(prev =>
            prev.map(m => m.id === aiId ? { ...m, content: m.content + token } : m)
          )
        },
        () => {
          setMessages(prev =>
            prev.map(m => m.id === aiId ? { ...m, streaming: false } : m)
          )
          setIsStreaming(false)
        }
      )
    } catch {
      // SSE failed — fall back to POST /chat
      try {
        const resp = await sendChat(query)
        setMessages(prev =>
          prev.map(m =>
            m.id === aiId
              ? {
                  ...m,
                  content: resp.answer,
                  intent: resp.intent,
                  latency_ms: resp.latency_ms,
                  sources: resp.sources as Source[],
                  streaming: false,
                }
              : m
          )
        )
      } catch {
        setMessages(prev =>
          prev.map(m =>
            m.id === aiId
              ? { ...m, content: 'Something went wrong. Please try again.', streaming: false }
              : m
          )
        )
      }
      setIsStreaming(false)
    }
  }, [])

  return { messages, isStreaming, sendMessage }
}
