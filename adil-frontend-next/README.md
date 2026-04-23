# Ask Aisha Frontend

Next.js web frontend for the Ask Aisha Islamic library assistant.

**Live:** https://frontend-production-d4c6.up.railway.app

## Tech Stack

- **Next.js 16** (App Router, TypeScript)
- **Tailwind CSS v4** (`@import "tailwindcss"` + `@theme` in `globals.css`)
- **react-markdown** + remark-gfm for answer rendering
- **Playwright** for E2E testing (45 tests)
- **Railway** deployment via Dockerfile

## Pages

| Route | Type | Description |
|-------|------|-------------|
| `/` | Client | Homepage -- centered search with starter prompts and tier selector |
| `/chat/[id]` | Client | Split-panel chat -- conversation left, sources right |
| `/library` | Client | Sortable book table with search and genre filter |
| `/library/[bookId]` | SSR | Book detail with SEO metadata |
| `/hadith` | Client | Hadith grading lookup with spectrum bar |
| `/api/health` | API | Health check endpoint |

## Development

```bash
npm install
npm run dev          # http://localhost:3000
npm run build        # production build
npm run lint         # ESLint
```

### Environment Variables

```bash
NEXT_PUBLIC_RAG_API_URL=https://rag-api-production-366d.up.railway.app
RAG_API_INTERNAL_URL=http://rag-api.railway.internal:8000  # Railway internal (SSR only)
```

## Testing

```bash
npx playwright test                    # all 45 tests
npx playwright test -g "Journey"       # multi-step journeys (6 tests)
npx playwright test -g "Homepage"      # single category
npx playwright test --reporter=html    # HTML report
```

### Test Coverage

- **Homepage** (8) -- title, dynamic book count, search input, starters, tier persistence
- **Navigation** (5) -- links, active states, routing
- **Library** (7) -- table loading, sorting, search, genre filter
- **Book Detail** (4) -- SSR rendering, back links, 404
- **Hadith Grader** (4) -- form, Grade button, loading state
- **Chat Flow** (5) -- E2E query, split panel, sources, bibliography toggle
- **Health** (1) -- 200 OK
- **Mobile** (4) -- responsive layout, sources toggle
- **Error** (1) -- 404 routing
- **Multi-step Journeys** (6):
  - Library search -> book detail -> "Ask about this book"
  - Chat query -> follow-up with conversation continuity
  - Citation workflow: Cards -> Bibliography -> Chicago/Harvard/APA -> copy
  - Tier selection persistence across pages
  - Mobile: search -> chat -> show/hide sources
  - Cross-page navigation without errors

All journey tests include **output sanity checks** (e.g., fasting answers mention Ramadan, citations contain author names).

## Key Components

```
components/
  nav.tsx               # Top navigation with active link highlighting
  search-input.tsx      # Reusable search input with loading state
  tier-selector.tsx     # Layman/Student/Scholar pills (localStorage)
  chat/
    message.tsx         # Markdown-rendered message with citation buttons
    source-card.tsx     # Source card with book info, type badge
    sources-panel.tsx   # Cards/Bibliography toggle, citation styles
    hadith-grading.tsx  # Collapsible hadith grading panel
  library/
    book-table.tsx      # Sortable table with genre badges
    genre-badge.tsx     # Color-coded genre pill
  hadith/
    grading-table.tsx   # Scholar grading results table
    spectrum-bar.tsx    # Visual opinion distribution bar

lib/
  api.ts                # RAG API client (server/client URL switching)
  types.ts              # TypeScript interfaces matching API models
  citations.ts          # Chicago/Harvard/APA citation formatting
  use-book-count.ts     # Hook for dynamic book count from /health
```

## Tailwind v4

This project uses **Tailwind CSS v4**. Key differences from v3:

- Config is in `app/globals.css` using `@theme` block (no `tailwind.config.ts`)
- `@import "tailwindcss"` instead of `@tailwind` directives
- Plugins via `@plugin` directive
- Content sources via `@source` directive

## Deployment

Railway service with Dockerfile (Node 20 Alpine, standalone output):

```bash
railway service link frontend
railway up                        # CLI upload from frontend/ directory
```

Railway settings: root directory = `frontend`, port = 8080.
