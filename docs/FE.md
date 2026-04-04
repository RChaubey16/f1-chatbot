# F1 Chatbot Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js 15 frontend for the F1 Chatbot with a split-panel layout: streaming chat on the left, live season standings on the right, styled with an F1 dark theme.

**Architecture:** A standalone Next.js 15 (App Router, TypeScript) project in `frontend/`, deployed to Vercel. The backend FastAPI app gains two new endpoints (`GET /standings/drivers`, `GET /standings/constructors`) that the frontend uses to populate the standings sidebar. Chat uses SSE streaming from the existing `GET /chat/stream` endpoint.

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS v4, shadcn/ui, Vitest + React Testing Library (frontend tests), pytest + respx (backend tests).

---

## File Map

### Backend additions

| File | Action | Purpose |
|---|---|---|
| `api/schemas.py` | Modify | Add `DriverStanding` and `ConstructorStanding` Pydantic models |
| `api/routes/standings.py` | Create | `GET /standings/drivers` and `GET /standings/constructors` |
| `api/main.py` | Modify | Register standings router |
| `api/routes/health.py` | Modify | Add production Vercel URL to CORS allowed origins (Task 10) |
| `tests/test_standings.py` | Create | Backend tests for new standings endpoints |

### Frontend (`frontend/`)

| File | Action | Purpose |
|---|---|---|
| `frontend/` | Create | Next.js 15 project root (scaffolded via CLI) |
| `frontend/app/globals.css` | Modify | F1 CSS custom properties + Tailwind base |
| `frontend/app/layout.tsx` | Modify | Root layout with `<Navbar>` and dark background |
| `frontend/app/page.tsx` | Modify | Single page — renders `<SplitLayout>` |
| `frontend/lib/types.ts` | Create | All shared TypeScript interfaces |
| `frontend/lib/api.ts` | Create | `streamChat()`, `fetchDriverStandings()`, `fetchConstructorStandings()`, `checkHealth()` |
| `frontend/hooks/useChat.ts` | Create | Message state + SSE streaming logic |
| `frontend/hooks/useStandings.ts` | Create | Fetch + cache standings, 6-hour refresh |
| `frontend/components/chat/ChatPanel.tsx` | Create | Scrollable message list + input area |
| `frontend/components/chat/MessageBubble.tsx` | Create | User / AI message bubble |
| `frontend/components/chat/SourceChip.tsx` | Create | Source citation pill |
| `frontend/components/chat/ChatInput.tsx` | Create | Textarea + send button |
| `frontend/components/standings/StandingsPanel.tsx` | Create | Right column with tabs + list |
| `frontend/components/standings/StandingsTabs.tsx` | Create | Drivers / Constructors tab switcher |
| `frontend/components/standings/StandingsRow.tsx` | Create | Single driver/constructor row |
| `frontend/components/layout/Navbar.tsx` | Create | Top nav with brand + API status |
| `frontend/components/layout/SplitLayout.tsx` | Create | Two-column wrapper |
| `frontend/__tests__/useChat.test.ts` | Create | Hook unit tests |
| `frontend/__tests__/useStandings.test.ts` | Create | Hook unit tests |
| `frontend/__tests__/MessageBubble.test.tsx` | Create | Component render tests |
| `frontend/vitest.config.ts` | Create | Vitest config |
| `frontend/.env.local` | Create | `NEXT_PUBLIC_API_URL=http://localhost:8000` |
| `frontend/vercel.json` | Create | Vercel deployment config |

---

## Task 1: Backend — Standings schemas + endpoints

**Files:**
- Modify: `api/schemas.py`
- Create: `api/routes/standings.py`
- Modify: `api/main.py`
- Create: `tests/test_standings.py`

### Step 1.1: Write failing backend tests

- [ ] Create `tests/test_standings.py`:

```python
"""Tests for GET /standings/drivers and GET /standings/constructors."""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock, AsyncMock

_JOLPICA_DRIVERS_URL = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"
_JOLPICA_CONSTRUCTORS_URL = "https://api.jolpi.ca/ergast/f1/current/constructorStandings.json"


def _driver_standings_payload() -> dict:
    return {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "DriverStandings": [
                            {
                                "position": "1",
                                "points": "136",
                                "Driver": {"givenName": "Max", "familyName": "Verstappen"},
                                "Constructors": [{"name": "Red Bull Racing"}],
                            },
                            {
                                "position": "2",
                                "points": "113",
                                "Driver": {"givenName": "Lando", "familyName": "Norris"},
                                "Constructors": [{"name": "McLaren"}],
                            },
                        ]
                    }
                ]
            }
        }
    }


def _constructor_standings_payload() -> dict:
    return {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "ConstructorStandings": [
                            {
                                "position": "1",
                                "points": "249",
                                "Constructor": {"name": "Red Bull Racing"},
                            },
                            {
                                "position": "2",
                                "points": "174",
                                "Constructor": {"name": "McLaren"},
                            },
                        ]
                    }
                ]
            }
        }
    }


@pytest.fixture()
async def test_client():
    from api.main import app
    mock_agent = MagicMock()
    mock_agent.close = AsyncMock()
    app.state.agent = mock_agent
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_driver_standings_success(test_client):
    with respx.mock:
        respx.get(_JOLPICA_DRIVERS_URL).mock(
            return_value=httpx.Response(200, json=_driver_standings_payload())
        )
        response = await test_client.get("/standings/drivers")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["position"] == 1
    assert data[0]["driver"] == "Max Verstappen"
    assert data[0]["team"] == "Red Bull Racing"
    assert data[0]["points"] == 136


@pytest.mark.asyncio
async def test_driver_standings_api_error_returns_503(test_client):
    with respx.mock:
        respx.get(_JOLPICA_DRIVERS_URL).mock(return_value=httpx.Response(503))
        response = await test_client.get("/standings/drivers")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_constructor_standings_success(test_client):
    with respx.mock:
        respx.get(_JOLPICA_CONSTRUCTORS_URL).mock(
            return_value=httpx.Response(200, json=_constructor_standings_payload())
        )
        response = await test_client.get("/standings/constructors")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["position"] == 1
    assert data[0]["team"] == "Red Bull Racing"
    assert data[0]["points"] == 249


@pytest.mark.asyncio
async def test_constructor_standings_api_error_returns_503(test_client):
    with respx.mock:
        respx.get(_JOLPICA_CONSTRUCTORS_URL).mock(return_value=httpx.Response(503))
        response = await test_client.get("/standings/constructors")

    assert response.status_code == 503
```

### Step 1.2: Run tests to confirm they fail

- [ ] Run:
```bash
uv run python -m pytest tests/test_standings.py -v
```
Expected: `FAILED` — `404 Not Found` (endpoints don't exist yet).

### Step 1.3: Add Pydantic schemas

- [ ] Open `api/schemas.py` and append:

```python
class DriverStanding(BaseModel):
    position: int
    driver: str
    team: str
    points: int


class ConstructorStanding(BaseModel):
    position: int
    team: str
    points: int
```

### Step 1.4: Create the standings router

- [ ] Create `api/routes/standings.py`:

```python
"""Standings endpoints — fetches current season standings from Jolpica."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from api.schemas import ConstructorStanding, DriverStanding
from ingestion.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/standings")

_JOLPICA_DRIVERS = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"
_JOLPICA_CONSTRUCTORS = "https://api.jolpi.ca/ergast/f1/current/constructorStandings.json"


@router.get("/drivers", response_model=list[DriverStanding])
async def driver_standings() -> list[DriverStanding]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_JOLPICA_DRIVERS)
            resp.raise_for_status()
            data = resp.json()
        rows = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
    except Exception as exc:
        log.warning("driver_standings fetch failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Standings unavailable") from exc

    return [
        DriverStanding(
            position=int(r["position"]),
            driver=f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
            team=r["Constructors"][0]["name"],
            points=int(r["points"]),
        )
        for r in rows
    ]


@router.get("/constructors", response_model=list[ConstructorStanding])
async def constructor_standings() -> list[ConstructorStanding]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_JOLPICA_CONSTRUCTORS)
            resp.raise_for_status()
            data = resp.json()
        rows = data["MRData"]["StandingsTable"]["StandingsLists"][0]["ConstructorStandings"]
    except Exception as exc:
        log.warning("constructor_standings fetch failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Standings unavailable") from exc

    return [
        ConstructorStanding(
            position=int(r["position"]),
            team=r["Constructor"]["name"],
            points=int(r["points"]),
        )
        for r in rows
    ]
```

### Step 1.5: Register the router in `api/main.py`

- [ ] Add the import and include after the existing routers:

```python
import api.routes.standings as standings_router
```

Add after `app.include_router(health_router.router)`:

```python
app.include_router(standings_router.router)
```

### Step 1.6: Run tests to confirm they pass

- [ ] Run:
```bash
uv run python -m pytest tests/test_standings.py -v
```
Expected: `4 passed`.

### Step 1.7: Run full test suite to confirm no regressions

- [ ] Run:
```bash
uv run python -m pytest tests/ -v
```
Expected: all tests pass.

### Step 1.8: Commit

- [ ] Run:
```bash
git add api/schemas.py api/routes/standings.py api/main.py tests/test_standings.py
git commit -m "feat: add /standings/drivers and /standings/constructors endpoints"
```

---

## Task 2: Frontend scaffold

**Files:**
- Create: `frontend/` (entire Next.js project)
- Modify: `frontend/app/globals.css`
- Create: `frontend/.env.local`
- Create: `frontend/vitest.config.ts`

### Step 2.1: Scaffold the Next.js 15 app

- [ ] From the repo root, run:
```bash
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*" \
  --no-eslint
```
Accept all defaults. This creates `frontend/` with Next.js 15, TypeScript, Tailwind CSS v4, and App Router.

### Step 2.2: Install shadcn/ui

- [ ] Run:
```bash
cd frontend
npx shadcn@latest init --defaults
```
When prompted, select: Style → **Default**, Base color → **Neutral**, CSS variables → **Yes**.

### Step 2.3: Install Vitest + React Testing Library

- [ ] Run:
```bash
cd frontend
npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom msw
```

### Step 2.4: Create Vitest config

- [ ] Create `frontend/vitest.config.ts`:

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, '.') },
  },
})
```

- [ ] Create `frontend/vitest.setup.ts`:

```typescript
import '@testing-library/jest-dom'
```

### Step 2.5: Add test script to package.json

- [ ] Open `frontend/package.json` and add to `"scripts"`:
```json
"test": "vitest run",
"test:watch": "vitest"
```

### Step 2.6: Set F1 CSS variables in globals.css

- [ ] Replace the contents of `frontend/app/globals.css` with:

```css
@import "tailwindcss";

:root {
  --f1-red: #E10600;
  --f1-bg: #0a0a0a;
  --f1-surface: #111111;
  --f1-surface-2: #1a1a1a;
  --f1-border: #1f1f1f;
  --f1-text: #e0e0e0;
  --f1-muted: #555555;
}

body {
  background-color: var(--f1-bg);
  color: var(--f1-text);
  font-family: var(--font-geist-sans), -apple-system, sans-serif;
}

* {
  box-sizing: border-box;
}
```

### Step 2.7: Create .env.local

- [ ] Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Step 2.8: Add .env.local to .gitignore

- [ ] Open `frontend/.gitignore` (created by scaffold) and confirm `.env.local` is listed. If not, add it:
```
.env.local
```

### Step 2.9: Verify dev server starts

- [ ] Run:
```bash
cd frontend && npm run dev
```
Expected: `▲ Next.js 15.x.x` — ready on `http://localhost:3000`. Stop with Ctrl+C.

### Step 2.10: Commit

- [ ] Run from repo root:
```bash
git add frontend/
git commit -m "feat: scaffold Next.js 15 frontend with Tailwind and shadcn/ui"
```

---

## Task 3: Types + API client

**Files:**
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/api.ts`

### Step 3.1: Create shared types

- [ ] Create `frontend/lib/types.ts`:

```typescript
export interface ChatRequest {
  query: string
  max_chunks?: number
}

export interface Source {
  content_type: string
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
```

### Step 3.2: Create API client

- [ ] Create `frontend/lib/api.ts`:

```typescript
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

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value, { stream: true })
    for (const line of chunk.split('\n')) {
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
```

### Step 3.3: Commit

- [ ] Run:
```bash
git add frontend/lib/
git commit -m "feat: add frontend types and API client"
```

---

## Task 4: useChat hook

**Files:**
- Create: `frontend/hooks/useChat.ts`
- Create: `frontend/__tests__/useChat.test.ts`

### Step 4.1: Write failing tests

- [ ] Create `frontend/__tests__/useChat.test.ts`:

```typescript
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
```

### Step 4.2: Run to confirm failure

- [ ] Run:
```bash
cd frontend && npm test
```
Expected: `FAIL` — `Cannot find module '@/hooks/useChat'`.

### Step 4.3: Implement the hook

- [ ] Create `frontend/hooks/useChat.ts`:

```typescript
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
```

### Step 4.4: Run tests to confirm pass

- [ ] Run:
```bash
cd frontend && npm test
```
Expected: `5 passed`.

### Step 4.5: Commit

- [ ] Run:
```bash
git add frontend/hooks/useChat.ts frontend/__tests__/useChat.test.ts
git commit -m "feat: add useChat hook with SSE streaming and fallback"
```

---

## Task 5: useStandings hook

**Files:**
- Create: `frontend/hooks/useStandings.ts`
- Create: `frontend/__tests__/useStandings.test.ts`

### Step 5.1: Write failing tests

- [ ] Create `frontend/__tests__/useStandings.test.ts`:

```typescript
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
```

### Step 5.2: Run to confirm failure

- [ ] Run:
```bash
cd frontend && npm test -- useStandings
```
Expected: `FAIL` — `Cannot find module '@/hooks/useStandings'`.

### Step 5.3: Implement the hook

- [ ] Create `frontend/hooks/useStandings.ts`:

```typescript
'use client'

import { useState, useEffect } from 'react'
import { fetchDriverStandings, fetchConstructorStandings } from '@/lib/api'
import type { DriverStanding, ConstructorStanding } from '@/lib/types'

const SIX_HOURS_MS = 6 * 60 * 60 * 1000

export function useStandings() {
  const [drivers, setDrivers] = useState<DriverStanding[]>([])
  const [constructors, setConstructors] = useState<ConstructorStanding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = async () => {
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
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, SIX_HOURS_MS)
    return () => clearInterval(interval)
  }, [])

  return { drivers, constructors, loading, error }
}
```

### Step 5.4: Run tests to confirm pass

- [ ] Run:
```bash
cd frontend && npm test
```
Expected: all tests pass.

### Step 5.5: Commit

- [ ] Run:
```bash
git add frontend/hooks/useStandings.ts frontend/__tests__/useStandings.test.ts
git commit -m "feat: add useStandings hook with 6-hour polling"
```

---

## Task 6: Chat components

**Files:**
- Create: `frontend/components/chat/SourceChip.tsx`
- Create: `frontend/components/chat/MessageBubble.tsx`
- Create: `frontend/components/chat/ChatInput.tsx`
- Create: `frontend/components/chat/ChatPanel.tsx`
- Create: `frontend/__tests__/MessageBubble.test.tsx`

### Step 6.1: Write failing component tests

- [ ] Create `frontend/__tests__/MessageBubble.test.tsx`:

```typescript
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
```

### Step 6.2: Run to confirm failure

- [ ] Run:
```bash
cd frontend && npm test -- MessageBubble
```
Expected: `FAIL` — `Cannot find module`.

### Step 6.3: Create SourceChip

- [ ] Create `frontend/components/chat/SourceChip.tsx`:

```tsx
import type { Source } from '@/lib/types'

interface Props {
  source: Source
}

export function SourceChip({ source }: Props) {
  return (
    <span className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] border"
      style={{ background: 'var(--f1-surface-2)', borderColor: 'var(--f1-border)', color: 'var(--f1-muted)' }}>
      <span style={{ color: 'var(--f1-red)' }}>◈</span>
      {source.source}
      {source.content_type ? ` · ${source.content_type}` : ''}
    </span>
  )
}
```

### Step 6.4: Create MessageBubble

- [ ] Create `frontend/components/chat/MessageBubble.tsx`:

```tsx
import type { Message } from '@/lib/types'
import { SourceChip } from './SourceChip'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
        style={
          isUser
            ? { background: 'var(--f1-surface-2)', border: '1px solid var(--f1-border)', color: 'var(--f1-muted)' }
            : { background: 'var(--f1-red)', color: '#fff' }
        }
      >
        {isUser ? 'U' : 'F1'}
      </div>

      {/* Content */}
      <div className={`flex flex-col gap-2 max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Intent + latency (AI only) */}
        {!isUser && message.intent && (
          <div className="flex items-center gap-2 text-[11px]" style={{ color: 'var(--f1-muted)' }}>
            <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide"
              style={{ background: 'var(--f1-surface-2)', border: '1px solid var(--f1-border)', color: 'var(--f1-red)' }}>
              {message.intent}
            </span>
            {message.latency_ms != null && <span>· {Math.round(message.latency_ms)}ms</span>}
          </div>
        )}

        {/* Bubble */}
        <div
          className="rounded-xl px-4 py-3 text-sm leading-relaxed"
          style={
            isUser
              ? { background: 'var(--f1-surface-2)', border: '1px solid var(--f1-border)', borderRadius: '12px 2px 12px 12px' }
              : { background: '#160000', border: '1px solid #2a0000', borderRadius: '2px 12px 12px 12px' }
          }
        >
          {message.streaming && !message.content ? (
            <div className="streaming-dots flex gap-1 items-center py-1">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    background: 'var(--f1-red)',
                    animation: `bounce 1.2s ${i * 0.2}s infinite`,
                  }}
                />
              ))}
            </div>
          ) : (
            message.content
          )}
        </div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.sources.map((s, i) => (
              <SourceChip key={i} source={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

### Step 6.5: Create ChatInput

- [ ] Create `frontend/components/chat/ChatInput.tsx`:

```tsx
'use client'

import { useState, useRef, KeyboardEvent } from 'react'

interface Props {
  onSend: (query: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const q = value.trim()
    if (!q || disabled) return
    onSend(q)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  return (
    <div className="flex gap-2 items-end p-4 border-t" style={{ borderColor: 'var(--f1-border)', background: '#0d0d0d' }}>
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder="Ask about F1 history or the current season..."
        className="flex-1 resize-none rounded-lg px-3.5 py-2.5 text-sm outline-none disabled:opacity-50"
        style={{
          background: 'var(--f1-surface-2)',
          border: '1px solid var(--f1-border)',
          color: 'var(--f1-text)',
          fontFamily: 'inherit',
          lineHeight: '1.5',
        }}
        onFocus={e => e.target.style.borderColor = 'var(--f1-red)'}
        onBlur={e => e.target.style.borderColor = 'var(--f1-border)'}
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="flex-shrink-0 rounded-lg px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
        style={{ background: 'var(--f1-red)' }}
      >
        Send
      </button>
    </div>
  )
}
```

### Step 6.6: Create ChatPanel

- [ ] Create `frontend/components/chat/ChatPanel.tsx`:

```tsx
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
```

### Step 6.7: Run tests to confirm pass

- [ ] Run:
```bash
cd frontend && npm test
```
Expected: all tests pass including `MessageBubble`.

### Step 6.8: Commit

- [ ] Run:
```bash
git add frontend/components/chat/ frontend/__tests__/MessageBubble.test.tsx
git commit -m "feat: add chat components (ChatPanel, MessageBubble, ChatInput, SourceChip)"
```

---

## Task 7: Standings components

**Files:**
- Create: `frontend/components/standings/StandingsTabs.tsx`
- Create: `frontend/components/standings/StandingsRow.tsx`
- Create: `frontend/components/standings/StandingsPanel.tsx`

> No separate tests needed — `useStandings` is tested in Task 5; components are simple presentational wrappers.

### Step 7.1: Create team color map

- [ ] Create `frontend/lib/teamColors.ts`:

```typescript
export const TEAM_COLORS: Record<string, string> = {
  'Red Bull Racing': '#3671C6',
  'McLaren': '#FF8000',
  'Ferrari': '#E8002D',
  'Mercedes': '#00A3E0',
  'Aston Martin': '#229971',
  'Alpine': '#FF87BC',
  'Williams': '#64C4FF',
  'RB': '#6692FF',
  'Kick Sauber': '#52E252',
  'Haas F1 Team': '#B6BABD',
}

export function getTeamColor(team: string): string {
  return TEAM_COLORS[team] ?? '#666666'
}
```

### Step 7.2: Create StandingsTabs

- [ ] Create `frontend/components/standings/StandingsTabs.tsx`:

```tsx
interface Props {
  active: 'drivers' | 'constructors'
  onChange: (tab: 'drivers' | 'constructors') => void
}

export function StandingsTabs({ active, onChange }: Props) {
  const tabs = [
    { key: 'drivers', label: 'Drivers' },
    { key: 'constructors', label: 'Constructors' },
  ] as const

  return (
    <div className="flex border-b" style={{ borderColor: 'var(--f1-border)' }}>
      {tabs.map(tab => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className="flex-1 py-2 text-xs font-medium transition-colors border-b-2"
          style={{
            color: active === tab.key ? 'var(--f1-red)' : 'var(--f1-muted)',
            borderBottomColor: active === tab.key ? 'var(--f1-red)' : 'transparent',
            background: 'transparent',
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
```

### Step 7.3: Create StandingsRow

- [ ] Create `frontend/components/standings/StandingsRow.tsx`:

```tsx
import { getTeamColor } from '@/lib/teamColors'

interface Props {
  position: number
  name: string   // driver full name or constructor name
  team?: string  // only for driver rows
  points: number
}

export function StandingsRow({ position, name, team, points }: Props) {
  const teamName = team ?? name
  const color = getTeamColor(teamName)
  const isTop3 = position <= 3

  return (
    <div className="flex items-center gap-2.5 px-5 py-2 border-b hover:bg-white/5 transition-colors"
      style={{ borderColor: 'var(--f1-border)' }}>
      <span className="w-5 text-center text-xs font-bold flex-shrink-0"
        style={{ color: isTop3 ? 'var(--f1-red)' : 'var(--f1-muted)' }}>
        {position}
      </span>
      <div className="w-0.5 h-7 rounded flex-shrink-0" style={{ background: color }} />
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-semibold truncate" style={{ color: 'var(--f1-text)' }}>
          {/* Abbreviate driver names (e.g. "Verstappen, M."); show constructor names in full */}
          {team
            ? `${name.split(' ').slice(-1)[0]}, ${name.split(' ')[0][0]}.`
            : name}
        </div>
        {team && (
          <div className="text-[11px] truncate" style={{ color: 'var(--f1-muted)' }}>{team}</div>
        )}
      </div>
      <span className="text-[13px] font-bold flex-shrink-0" style={{ color: '#aaa' }}>
        {points}
      </span>
    </div>
  )
}
```

### Step 7.4: Create StandingsPanel

- [ ] Create `frontend/components/standings/StandingsPanel.tsx`:

```tsx
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
```

### Step 7.5: Run all tests

- [ ] Run:
```bash
cd frontend && npm test
```
Expected: all tests pass.

### Step 7.6: Commit

- [ ] Run:
```bash
git add frontend/components/standings/ frontend/lib/teamColors.ts
git commit -m "feat: add standings panel components"
```

---

## Task 8: Root layout and page

**Files:**
- Create: `frontend/components/layout/Navbar.tsx`
- Create: `frontend/components/layout/SplitLayout.tsx`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/page.tsx`

### Step 8.1: Create Navbar

- [ ] Create `frontend/components/layout/Navbar.tsx`:

```tsx
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
```

### Step 8.2: Create SplitLayout

- [ ] Create `frontend/components/layout/SplitLayout.tsx`:

```tsx
import { ChatPanel } from '@/components/chat/ChatPanel'
import { StandingsPanel } from '@/components/standings/StandingsPanel'

export function SplitLayout() {
  return (
    <div className="flex flex-1 overflow-hidden">
      <ChatPanel />
      {/* Standings panel hidden on mobile, visible on md+ */}
      <div className="hidden md:flex">
        <StandingsPanel />
      </div>
    </div>
  )
}
```

### Step 8.3: Update root layout

- [ ] Replace the contents of `frontend/app/layout.tsx` with:

```tsx
import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'
import { Navbar } from '@/components/layout/Navbar'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'F1 Chatbot',
  description: 'Ask anything about Formula 1 history and the current season',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geist.className} flex flex-col h-screen overflow-hidden`}
        style={{ background: 'var(--f1-bg)' }}>
        <Navbar />
        {children}
      </body>
    </html>
  )
}
```

### Step 8.4: Update page

- [ ] Replace the contents of `frontend/app/page.tsx` with:

```tsx
import { SplitLayout } from '@/components/layout/SplitLayout'

export default function Home() {
  return <SplitLayout />
}
```

### Step 8.5: Add bounce keyframe animation to globals.css

- [ ] Append to `frontend/app/globals.css`:

```css
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}
```

### Step 8.6: Verify the app renders

- [ ] Run:
```bash
cd frontend && npm run dev
```
Open `http://localhost:3000`. Expected: F1 dark theme, split layout with chat panel and standings sidebar.

### Step 8.7: Run all tests

- [ ] Run:
```bash
cd frontend && npm test
```
Expected: all tests pass.

### Step 8.8: Commit

- [ ] Run:
```bash
git add frontend/components/layout/ frontend/app/layout.tsx frontend/app/page.tsx frontend/app/globals.css
git commit -m "feat: add root layout, navbar, and split layout page"
```

---

## Task 9: CORS update for production

**Files:**
- Modify: `api/main.py`

The FastAPI app needs to allow requests from the Vercel deployment URL. When that URL is known, add it to the CORS middleware.

### Step 9.1: Add CORS middleware to api/main.py

- [ ] Open `api/main.py` and update it to:

```python
"""F1 Chatbot FastAPI application."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.agent import Agent
from ingestion.scheduler import create_scheduler
from ingestion.core.logging import get_logger

import api.routes.chat as chat_router
import api.routes.health as health_router
import api.routes.standings as standings_router

log = get_logger(__name__)

_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    os.environ.get("FRONTEND_URL", ""),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting F1 Chatbot API")
    app.state.agent = Agent()
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("Startup complete")

    yield

    log.info("Shutting down F1 Chatbot API")
    try:
        app.state.scheduler.shutdown(wait=False)
    except Exception:
        log.warning("Scheduler was not running on shutdown")
    await app.state.agent.close()
    log.info("Shutdown complete")


app = FastAPI(
    title="F1 Chatbot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _ALLOWED_ORIGINS if o],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(chat_router.router)
app.include_router(health_router.router)
app.include_router(standings_router.router)
```

### Step 9.2: Add FRONTEND_URL to .env.example

- [ ] Open `.env.example` and append:
```bash
# CORS — set to your Vercel deployment URL in production
FRONTEND_URL=https://your-app.vercel.app
```

### Step 9.3: Run full backend test suite

- [ ] Run:
```bash
uv run python -m pytest tests/ -v
```
Expected: all tests pass.

### Step 9.4: Commit

- [ ] Run:
```bash
git add api/main.py .env.example
git commit -m "feat: add CORS middleware with configurable frontend URL"
```

---

## Task 10: Vercel deployment

**Files:**
- Create: `frontend/vercel.json`

### Step 10.1: Create vercel.json

- [ ] Create `frontend/vercel.json`:

```json
{
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "env": {
    "NEXT_PUBLIC_API_URL": "@f1_api_url"
  }
}
```

### Step 10.2: Create Vercel environment secret

- [ ] In the Vercel dashboard for the project, go to **Settings → Environment Variables** and add:
  - Key: `NEXT_PUBLIC_API_URL`
  - Value: `https://your-api-host.com` (the URL where the FastAPI backend is deployed)

### Step 10.3: Deploy to Vercel

- [ ] From `frontend/`:
```bash
npx vercel --prod
```
Or connect the GitHub repo in the Vercel dashboard and set the **Root Directory** to `frontend/`.

### Step 10.4: Update FRONTEND_URL in backend .env

- [ ] Once Vercel provides the deployment URL (e.g. `https://f1-chatbot.vercel.app`), set it in the backend `.env`:
```bash
FRONTEND_URL=https://f1-chatbot.vercel.app
```
Restart the backend API for the change to take effect.

### Step 10.5: Smoke test production

- [ ] Open the Vercel URL in a browser
- [ ] Confirm: F1 theme renders, navbar shows "API Connected", standings panel loads
- [ ] Send a test query: "Who won the 2023 championship?"
- [ ] Confirm: streamed response appears token-by-token with intent badge and source chips

### Step 10.6: Final commit

- [ ] Run:
```bash
git add frontend/vercel.json
git commit -m "feat: add Vercel deployment config"
```

---

## Done

All tasks complete. The frontend is live on Vercel with:
- F1 dark theme split layout
- Streaming chat via SSE
- Live standings sidebar (drivers + constructors) with team colours
- API health indicator in navbar
- Graceful error handling (stream fallback, offline banner, unavailable standings)
