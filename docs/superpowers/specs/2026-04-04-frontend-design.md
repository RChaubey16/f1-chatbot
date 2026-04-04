# F1 Chatbot — Frontend Design Spec

**Date:** 2026-04-04  
**Status:** Approved

---

## Summary

A Next.js 15 (App Router) frontend for the F1 Chatbot, deployed to Vercel. The UI is a desktop-first split layout: a streaming chat panel on the left and a live standings sidebar on the right, styled with an F1-branded dark theme (dark background, #E10600 red accents). Each query is single-turn — no conversation history. Tailwind CSS + shadcn/ui for components.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS v4 |
| Components | shadcn/ui |
| Deployment | Vercel |
| API target | FastAPI backend (existing) |

---

## Architecture

```
frontend/                      ← Next.js 15 App Router project
├── app/
│   ├── layout.tsx             ← Root layout: navbar + dark theme
│   ├── page.tsx               ← Single page: SplitLayout
│   └── globals.css            ← Tailwind base + F1 custom vars
├── components/
│   ├── chat/
│   │   ├── ChatPanel.tsx      ← Left column: message list + input
│   │   ├── MessageBubble.tsx  ← Individual user/AI message
│   │   ├── SourceChip.tsx     ← Source citation pill
│   │   └── ChatInput.tsx      ← Textarea + send button
│   └── standings/
│       ├── StandingsPanel.tsx ← Right column: tabs + list
│       ├── StandingsRow.tsx   ← Single driver/constructor row
│       └── StandingsTabs.tsx  ← Drivers / Constructors tab switcher
├── lib/
│   ├── api.ts                 ← Typed fetch wrappers for /chat, /chat/stream, /health
│   └── types.ts               ← ChatRequest, ChatResponse, Source, Standing types
└── hooks/
    ├── useChat.ts             ← Manages messages state, calls streamChat()
    └── useStandings.ts        ← Fetches + caches standings from /chat (tools)
```

---

## Layout

**Split layout — desktop first:**

```
┌─────────────────────────────────────────────────────────┐
│  [F1] Chatbot                          ● API Connected  │  ← Navbar (52px, red bottom border)
├──────────────────────────────┬──────────────────────────┤
│                              │  2025 Season             │
│   CHAT PANEL                 │  ──────────────────────  │
│                              │  [Drivers] [Constructors]│
│   [AI bubble]                │                          │
│   [User bubble]              │  1  ▌ M. Verstappen 136  │
│   [AI bubble + sources]      │  2  ▌ L. Norris     113  │
│   [streaming dots...]        │  3  ▌ C. Leclerc     98  │
│                              │  ...                     │
│   ─────────────────────────  │                          │
│   [textarea      ] [Send]    │  Updated via OpenF1 · 6h │
└──────────────────────────────┴──────────────────────────┘
```

- Chat panel: `flex-1`, min-width 0, scrollable message list
- Standings panel: fixed `280px` width, scrollable rows
- On mobile (`< 768px`): standings panel collapses, chat takes full width

---

## Components

### ChatPanel
- Renders scrollable list of `MessageBubble` components
- Auto-scrolls to bottom on new message
- Shows streaming dots (3-dot bounce animation) while response is in flight
- Passes query to `useChat` hook on submit

### MessageBubble
- `role: "user" | "ai"` — determines alignment and styling
- AI bubbles show `intent` badge (HISTORICAL / CURRENT / MIXED) and latency in ms
- AI bubbles show list of `SourceChip` components below content
- SSE tokens are appended character-by-character to the AI bubble as they arrive

### ChatInput
- Multiline `<textarea>` (auto-grows up to 4 lines)
- Submit on Enter (Shift+Enter for newline), or Send button click
- Disabled while a response is streaming

### StandingsPanel
- Tabs: Drivers / Constructors
- Fetches standings once on mount via `useStandings`, polling every 6 hours
- Each `StandingRow` shows: position, team color bar, driver name, team name, points
- Team colors hardcoded to the 10 current constructors

---

## Data Flow

### Chat (streaming)

```
ChatInput submit
  → useChat.sendMessage(query)
  → GET /chat/stream?query=<query>   (SSE)
  → tokens appended to AI bubble in real time
  → "data: [DONE]" closes the stream
```

### Chat (fallback non-streaming)

```
  → POST /chat  { query }
  → full ChatResponse JSON
  → AI bubble rendered at once
```

Streaming is the default. Falls back to POST /chat if SSE fails.

### Standings

```
useStandings mount
  → GET /standings/drivers   → DriverStanding[]
  → GET /standings/constructors → ConstructorStanding[]
  → displayed in StandingsPanel
```

This requires adding two thin endpoints to the FastAPI backend (`GET /standings/drivers` and `GET /standings/constructors`) that call the existing `get_current_standings()` function in `agent/tools.py` and return structured JSON — avoiding fragile text parsing of chat responses.

Standings are fetched fresh on mount and re-fetched every 6 hours via `setInterval`.

---

## Theming

```css
:root {
  --f1-red:       #E10600;
  --f1-bg:        #0a0a0a;
  --f1-surface:   #111111;
  --f1-surface-2: #1a1a1a;
  --f1-border:    #1f1f1f;
  --f1-text:      #e0e0e0;
  --f1-muted:     #555555;
}
```

- Navbar bottom border: `2px solid var(--f1-red)`
- Send button: `bg-[--f1-red]`
- Intent badges, source chips: dark surface with red accent text
- Team color bars: hardcoded per constructor (Red Bull #3671C6, Ferrari #E8002D, McLaren #FF8000, Mercedes #00A3E0, etc.)

---

## API Integration

The frontend targets the existing FastAPI backend. Base URL is configured via `NEXT_PUBLIC_API_URL` environment variable (e.g. `http://localhost:8000` for dev, production API URL for Vercel).

```ts
// lib/types.ts
interface ChatRequest       { query: string; max_chunks?: number }
interface ChatResponse      { answer: string; sources: Source[]; intent: string; latency_ms: number }
interface Source            { content_type: string; source: string; metadata: Record<string, unknown> }
interface DriverStanding    { position: number; driver: string; team: string; points: number }
interface ConstructorStanding { position: number; team: string; points: number }
```

No auth required. CORS is already enabled on the FastAPI backend.

---

## Environment Variables

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000

# Vercel (production)
NEXT_PUBLIC_API_URL=https://your-api-host.com
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| API unreachable | Health check fails → banner "API offline" shown in navbar |
| Stream error mid-response | Partial bubble shown + "Response interrupted" note |
| `/chat` 500 | Error toast via shadcn/ui `useToast` |
| Standings fetch fails | Panel shows "—" for all values, no crash |

---

## Deployment

- **Frontend:** Vercel — auto-deploy on push to `main` from a `frontend/` subdirectory or a separate repo
- **Backend:** Existing FastAPI on any host (Docker, Fly.io, Railway, etc.)
- **CORS:** Already configured on backend; add production Vercel URL to allowed origins in `api/main.py`

---

## What's Out of Scope

- Multi-turn conversation / session history
- Authentication / user accounts
- Race calendar or lap-time visualisations
- Mobile-specific navigation (basic responsive collapse only)
