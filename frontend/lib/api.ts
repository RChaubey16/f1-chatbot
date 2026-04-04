import type { ChatResponse, DriverStanding, ConstructorStanding } from './types'

const base = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

/**
 * Opens an SSE stream for the given query.
 * Calls onToken for each streamed token, onDone when complete.
 */
export async function streamChat(
  query: string,
  onToken: (token: string) => void,
  onDone: () => void,
  signal?: AbortSignal
): Promise<void> {
  const url = `${base}/chat/stream?query=${encodeURIComponent(query)}`
  const response = await fetch(url, { signal })
  if (!response.ok || !response.body) {
    throw new Error(`Stream failed: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''  // last element may be incomplete

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (payload === '[DONE]') {
          onDone()
          return
        }
        try {
          const parsed = JSON.parse(payload) as { token: string }
          onToken(parsed.token)
        } catch {
          // skip malformed lines
        }
      }
    }

    // flush any remaining buffered bytes
    buffer += decoder.decode()
    for (const line of buffer.split('\n')) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') {
        onDone()
        return
      }
      try {
        const parsed = JSON.parse(payload) as { token: string }
        onToken(parsed.token)
      } catch {
        // skip malformed lines
      }
    }
  } finally {
    reader.releaseLock()
  }

  onDone()
}

/**
 * Non-streaming fallback — POST /chat.
 */
export async function sendChat(query: string): Promise<ChatResponse> {
  const response = await fetch(`${base}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (!response.ok) throw new Error(`Chat failed: ${response.status}`)
  return response.json() as Promise<ChatResponse>
}

export async function fetchDriverStandings(): Promise<DriverStanding[]> {
  const response = await fetch(`${base}/standings/drivers`)
  if (!response.ok) throw new Error(`Standings fetch failed: ${response.status}`)
  return response.json() as Promise<DriverStanding[]>
}

export async function fetchConstructorStandings(): Promise<ConstructorStanding[]> {
  const response = await fetch(`${base}/standings/constructors`)
  if (!response.ok) throw new Error(`Standings fetch failed: ${response.status}`)
  return response.json() as Promise<ConstructorStanding[]>
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${base}/health`)
    return response.ok
  } catch {
    return false
  }
}
