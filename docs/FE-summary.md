# Frontend Summary — Next.js Chat UI + Live Standings Sidebar

## Overview

The frontend is a Next.js 16 (App Router, TypeScript) single-page application
deployed to Vercel. It provides a split-panel layout: a streaming chat interface
on the left that communicates with the existing FastAPI backend via SSE, and a
live standings sidebar on the right that displays the current-season driver and
constructor standings. Two new backend endpoints (`GET /standings/drivers`,
`GET /standings/constructors`) were added to support the sidebar.

**Tech Stack:** Next.js 16.2.2, React 19, Tailwind CSS v4, TypeScript,
Vitest + React Testing Library (frontend tests), pytest + respx (backend tests).

---

## Architecture

```
Browser
  │
  ├── GET / → <SplitLayout>
  │     ├── <ChatPanel>   (left, flex-1)
  │     │     ├── Message list (scrollable)
  │     │     │     └── <MessageBubble> × N
  │     │     │           └── <SourceChip> × N (AI messages only)
  │     │     └── <ChatInput> (auto-resize textarea + Send button)
  │     └── <StandingsPanel> (right, 280px, hidden on mobile)
  │           ├── <StandingsTabs> (Drivers / Constructors)
  │           └── <StandingsRow> × N
  │
  ├── useChat  →  streamChat()  →  GET /chat/stream?query=...  (SSE primary)
  │                └─ fallback: sendChat()  →  POST /chat
  │
  └── useStandings  →  fetchDriverStandings()      →  GET /standings/drivers
                    →  fetchConstructorStandings()  →  GET /standings/constructors
                    (refreshes every 6 hours)


FastAPI backend (existing + new)
  ├── GET  /chat/stream     (SSE streaming — existing)
  ├── POST /chat            (JSON fallback — existing)
  ├── GET  /health          (existing)
  ├── GET  /standings/drivers       ← new
  └── GET  /standings/constructors  ← new
```

---

## Files Created

### Frontend (`frontend/`)

#### App Shell

| File | Purpose |
|------|---------|
| `app/globals.css` | F1 CSS custom properties + Tailwind v4 base import |
| `app/layout.tsx` | Root layout: Geist font, `<Navbar>`, dark F1 background |
| `app/page.tsx` | Single page — renders `<SplitLayout>` |

#### Data Layer

| File | Purpose |
|------|---------|
| `lib/types.ts` | All shared TypeScript interfaces |
| `lib/api.ts` | All fetch functions: `streamChat`, `sendChat`, `fetchDriverStandings`, `fetchConstructorStandings`, `checkHealth` |
| `lib/teamColors.ts` | `TEAM_COLORS` map and `getTeamColor(team)` helper |
| `lib/utils.ts` | `cn()` — `clsx` + `tailwind-merge` className utility |

#### Hooks

| File | Purpose |
|------|---------|
| `hooks/useChat.ts` | Message state + SSE streaming with POST fallback |
| `hooks/useStandings.ts` | Fetch driver + constructor standings on mount, 6h auto-refresh |

#### Components

| File | Purpose |
|------|---------|
| `components/layout/Navbar.tsx` | F1 brand mark + live API health dot (green / red) |
| `components/layout/SplitLayout.tsx` | `flex` row wrapper — chat left, standings right (hidden `md:` breakpoint) |
| `components/chat/ChatPanel.tsx` | Scrollable message list + `<ChatInput>`, `aria-live` region |
| `components/chat/MessageBubble.tsx` | User / AI bubble, intent badge, latency, streaming dots |
| `components/chat/ChatInput.tsx` | Auto-resize textarea, Enter to send (Shift+Enter for newline) |
| `components/chat/SourceChip.tsx` | Inline citation pill showing source name + content type |
| `components/standings/StandingsPanel.tsx` | 280px panel with header, tabs, scrollable list, and refresh footer |
| `components/standings/StandingsTabs.tsx` | Drivers / Constructors tab switcher with red underline indicator |
| `components/standings/StandingsRow.tsx` | Position number, team colour bar, name / team, points |
| `components/ui/button.tsx` | shadcn base button primitive |

#### Config / Tooling

| File | Purpose |
|------|---------|
| `vitest.config.ts` | Vitest + `@vitejs/plugin-react`, `jsdom` environment, `@` alias |
| `vitest.setup.ts` | `@testing-library/jest-dom` matchers |
| `vercel.json` | `nextjs` framework, `@f1_api_url` Vercel secret for `NEXT_PUBLIC_API_URL` |
| `package.json` | Dependencies: Next.js 16, React 19, Tailwind v4, Vitest, MSW, RTL |

#### Tests

| File | Tests | Purpose |
|------|------:|---------|
| `__tests__/MessageBubble.test.tsx` | 4 | Component render: user bubble, AI bubble, intent badge, streaming dots |
| `__tests__/useChat.test.ts` | 5 | Hook logic: initial state, user message append, token accumulation, streaming flag, POST fallback |
| `__tests__/useStandings.test.ts` | 3 | Hook logic: fetch on mount, error state, initial loading state |

---

### Backend additions

#### New files

| File | Purpose |
|------|---------|
| `api/routes/standings.py` | `GET /standings/drivers` and `GET /standings/constructors` — proxies Jolpica current-season standings |
| `tests/test_standings.py` | 5 tests for the new standing endpoints |

#### Modified files

| File | Change |
|------|--------|
| `api/schemas.py` | Added `DriverStanding` and `ConstructorStanding` Pydantic models |
| `api/main.py` | Registered `standings_router` |

---

## Key Implementation Details

### `lib/api.ts` — SSE stream parser

`streamChat` reads the SSE response body as a `ReadableStream`, accumulates
a `buffer`, splits on `\n`, and parses `data: {...}` lines:

```
data: {"token": "Max"}       → calls onToken("Max")
data: [DONE]                 → calls onDone(), returns
```

Any remaining bytes are flushed after the loop ends. A final `onDone()` call
is made if `[DONE]` was never received (handles premature stream close).

### `hooks/useChat.ts` — SSE primary, POST fallback

1. Immediately appends both the user message and a placeholder AI message
   (with `streaming: true`) to state so the UI renders the loading dots
   without delay.
2. Calls `streamChat` — each token is appended incrementally to the AI
   message's `content`.
3. If `streamChat` throws, falls back to `sendChat` (POST /chat) which also
   populates `intent`, `latency_ms`, and `sources` on the AI message.
4. `isStreaming` is set back to `false` via the `onDone` callback (SSE path)
   or in the `finally` block (fallback path).

### `hooks/useStandings.ts` — polling strategy

`useEffect` fires `load()` on mount, then registers a `setInterval` at 6 hours.
The interval is cleared on unmount. Both driver and constructor standings are
fetched in parallel with `Promise.all`.

### `components/standings/StandingsRow.tsx` — team colour bar

Each row renders a 2px-wide vertical bar coloured via `getTeamColor(teamName)`.
For driver rows `teamName = team`; for constructor rows `teamName = name`.
`getTeamColor` falls back to `#666666` for unknown teams. The row also formats
driver names as `"Lastname, F."` for compact display.

### `api/routes/standings.py` — thin Jolpica proxy

Both endpoints make a single `httpx.AsyncClient` GET to
`https://api.jolpi.ca/ergast/f1/current/...Standings.json`, parse the nested
`MRData.StandingsTable.StandingsLists[0]` structure, and map it to flat
`DriverStanding` / `ConstructorStanding` Pydantic models. Any exception
surfaces as HTTP 503 with `detail: "Standings unavailable"`.

### F1 dark theme (`globals.css`)

Custom properties defined on `:root` — no dark-mode toggle needed since the
app is always dark:

| Variable | Value | Usage |
|----------|-------|-------|
| `--f1-red` | `#E10600` | Accent colour (nav border, badges, send button, dots) |
| `--f1-bg` | `#0a0a0a` | Page background |
| `--f1-surface` | `#111111` | Navbar background |
| `--f1-surface-2` | `#1a1a1a` | User bubbles, input field, chips |
| `--f1-border` | `#1f1f1f` | All borders and dividers |
| `--f1-text` | `#e0e0e0` | Primary text |
| `--f1-muted` | `#555555` | Secondary text, timestamps, labels |

---

## Tests

### Frontend (Vitest + React Testing Library)

| File | Tests | Key assertions |
|------|------:|----------------|
| `__tests__/MessageBubble.test.tsx` | 4 | User content, AI content, intent badge render, streaming dots class |
| `__tests__/useChat.test.ts` | 5 | Empty initial state, user message appended, AI tokens accumulated, `isStreaming` flag cleared, POST fallback on SSE error |
| `__tests__/useStandings.test.ts` | 3 | Both endpoints fetched on mount, `error=true` on rejection, `loading=true` initially |
| **Frontend total** | **12** | |

### Backend (pytest + respx)

| File | Tests | Key assertions |
|------|------:|----------------|
| `tests/test_standings.py` | 5 | Driver standings 200 + shape, 503 on Jolpica error, constructor standings 200 + shape, 503 on error, empty list when season not started |
| **Backend total** | **5** | |

**All 17 new tests pass** (12 frontend, 5 backend). Grand total across all phases: **68 tests**.

---

## How to Run

```bash
# --- Frontend ---

cd frontend

# Install dependencies
pnpm install          # or: npm install

# Development (requires backend running on :8000)
pnpm dev              # http://localhost:3000

# Production build
pnpm build && pnpm start

# Run frontend tests
pnpm test

# --- Backend (standings endpoints) ---

# Start all services
docker compose up -d

# Verify new endpoints
curl http://localhost:8000/standings/drivers
curl http://localhost:8000/standings/constructors

# Run all backend tests
uv sync --extra dev
uv run python -m pytest tests/ -v
```

---

## Environment Variables

| Variable | Where | Description |
|----------|-------|-------------|
| `NEXT_PUBLIC_API_URL` | frontend `.env.local` | Backend base URL (default `http://localhost:8000`) |
| `FRONTEND_URL` | backend `.env` | Vercel production URL — added to CORS allowed origins |

Vercel reads `NEXT_PUBLIC_API_URL` from the `@f1_api_url` secret defined in
`vercel.json`. For local dev, create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Completion Criteria Status

- [x] Split-panel layout renders at `http://localhost:3000`
- [x] Chat streams tokens in real time via SSE
- [x] POST /chat fallback fires automatically on SSE failure
- [x] Driver and constructor standings load from `GET /standings/*`
- [x] Standings sidebar auto-refreshes every 6 hours
- [x] Team colour bars resolve for all 10 current constructors
- [x] Navbar shows live API health status
- [x] Standings panel hidden on mobile (`< md` breakpoint)
- [x] All 12 frontend tests pass (`pnpm test`)
- [x] All 5 new backend tests pass
- [x] Deployed to Vercel via `vercel.json`
