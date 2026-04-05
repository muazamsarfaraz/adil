# adil-frontend

![Deploy](https://img.shields.io/badge/deploy-Railway-blueviolet)
![Framework](https://img.shields.io/badge/framework-Chainlit-orange)

**AskAdil Frontend -- AI legal education chatbot for British Muslims.**

Part of [AskAdil by MCB](https://askadil.org) (Muslim Council of Britain).

---

## What It Does

AskAdil is a conversational AI interface that helps British Muslims understand their rights under UK discrimination and hate crime law. It provides accessible, culturally-sensitive legal education grounded in UK legislation and 1,000+ court judgments from The National Archives.

**This is not a law firm.** AskAdil educates users about their rights, helps them gather evidence, and connects them with the right organisations and solicitors when professional help is needed.

## Features

| Feature | Description |
|---------|-------------|
| **Multi-turn chat** | Contextual conversation with memory across turns |
| **Image analysis** | Upload screenshots and document photos for AI-powered legal analysis |
| **Media URL analysis** | Paste YouTube, Twitter/X, Facebook, Instagram, or news URLs for content extraction and legal analysis |
| **Hate crime reporting** | Guided PII collection and consent flow to submit reports to 8 UK targets (Police UK, BMT, IRU, Tell MAMA, etc.) |
| **Legislation lookup** | Specific section citations with links to legislation.gov.uk |
| **Viability scoring** | Structured assessment (0-100 score, Vento band, statutory footing, case law precedent) |
| **Solicitor directory** | 24 curated firms filterable by jurisdiction, specialism, and location |
| **Jurisdiction detection** | Auto-detects UK jurisdiction from IP address with confirm/change UI |
| **Report generation** | Incident summaries, solicitor consultation packs, and smart form guides |

---

## Quick Start

```bash
# Create .env
cp .env.example .env
# Edit .env: set RAG_API_URL and ADIL_API_KEY

# Install dependencies
pip install -r requirements.txt

# Run
chainlit run app.py --host 0.0.0.0 --port 8000
```

The frontend requires [adil-rag-api](../adil-rag-api) to be running as its backend.

---

## Configuration

| File | Purpose |
|------|---------|
| `.chainlit/config.toml` | Chainlit framework configuration (project name, theme, features) |
| `.chainlit/translations/` | UI string translations |
| `public/custom.css` | Custom theme overrides and branding styles |
| `public/custom.js` | Client-side JavaScript customisations |
| `public/theme.json` | Colour palette and theme variables |
| `public/logo_dark.svg` | Logo for dark mode |
| `public/logo_light.svg` | Logo for light mode |
| `public/favicon.svg` | Browser tab icon |
| `.env` | Runtime configuration (API URL, API key) |

---

## Deployment (Railway)

Deploys as a Docker container on Railway.

```bash
cd adil-frontend
railway link --project <PROJECT_ID> --environment production --service adil-frontend
railway up -d
```

**Live URL:** [askadil.org](https://askadil.org) (Cloudflare DNS -> Railway)

---

## Testing

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run Playwright E2E tests
python -m pytest tests/ -v
```

---

## License

Copyright Muslim Council of Britain. All rights reserved.
