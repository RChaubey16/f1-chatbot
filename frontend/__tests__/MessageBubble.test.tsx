import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MessageBubble } from '@/components/chat/MessageBubble'
import type { Message } from '@/lib/types'

const userMsg: Message = {
  id: '1',
  role: 'user',
  content: 'Who won the 1988 championship?',
}

const aiMsg: Message = {
  id: '2',
  role: 'ai',
  content: 'Ayrton Senna won.',
  intent: 'HISTORICAL',
  latency_ms: 142,
  sources: [{ content_type: 'race_result', source: 'jolpica', metadata: {} }],
}

const streamingMsg: Message = {
  id: '3',
  role: 'ai',
  content: '',
  streaming: true,
}

describe('MessageBubble', () => {
  it('renders user message content', () => {
    render(<MessageBubble message={userMsg} />)
    expect(screen.getByText('Who won the 1988 championship?')).toBeTruthy()
  })

  it('renders AI answer and intent badge', () => {
    render(<MessageBubble message={aiMsg} />)
    expect(screen.getByText('Ayrton Senna won.')).toBeTruthy()
    expect(screen.getByText('HISTORICAL')).toBeTruthy()
  })

  it('renders source chip for AI message', () => {
    render(<MessageBubble message={aiMsg} />)
    expect(screen.getByText(/jolpica/)).toBeTruthy()
  })

  it('renders streaming dots when streaming=true', () => {
    const { container } = render(<MessageBubble message={streamingMsg} />)
    expect(container.querySelector('.streaming-dots')).toBeTruthy()
  })
})
