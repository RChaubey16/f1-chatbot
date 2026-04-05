'use client'

import { useEffect, useRef } from 'react'
import { useChat } from '@/hooks/useChat'
import { MessageBubble } from './MessageBubble'
import { ChatInput } from './ChatInput'

export function ChatPanel() {
  const { messages, isStreaming, sendMessage } = useChat()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex flex-col flex-1 min-w-0 border-r" style={{ borderColor: 'var(--f1-border)' }}>
      {/* Message list */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-5 p-6">
        {messages.length === 0 && (
          <div className="flex gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white"
              style={{ background: 'var(--f1-red)' }}>
              F1
            </div>
            <div className="rounded-xl px-4 py-3 text-sm leading-relaxed max-w-[75%]"
              style={{ background: '#160000', border: '1px solid #2a0000', borderRadius: '2px 12px 12px 12px', color: 'var(--f1-text)' }}>
              Ask me anything about Formula 1 — race history from 1950 to today, driver stats, constructor battles, and live 2025 season updates.
            </div>
          </div>
        )}
        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={sendMessage} disabled={isStreaming} />
    </div>
  )
}
