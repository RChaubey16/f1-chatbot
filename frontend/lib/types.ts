export interface ChatRequest {
  query: string
  max_chunks?: number
}

export interface Source {
  content_type?: string
  source: string
  metadata: Record<string, unknown>
}

export interface ChatResponse {
  answer: string
  sources: Source[]
  intent: 'HISTORICAL' | 'CURRENT' | 'MIXED'
  latency_ms: number
}

export interface Message {
  id: string
  role: 'user' | 'ai'
  content: string
  intent?: ChatResponse['intent']
  latency_ms?: number
  sources?: Source[]
  streaming?: boolean
}

export interface DriverStanding {
  position: number
  driver: string
  team: string
  points: number
}

export interface ConstructorStanding {
  position: number
  team: string
  points: number
}
