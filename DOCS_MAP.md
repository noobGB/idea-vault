# Docs Map — what documents which part of the system

This repo has three doc files (`README.md`, `TECH_STACK.md`, `CLAUDE.md`) that each describe
several overlapping parts of the system from a different angle. Built proactively, before any
drift has happened — `snowpro-core-prep`'s own `DOCS_MAP.md` exists because a real feature there
shipped correctly while docs quietly kept describing the *previous* architecture; this file exists
so that never needs to happen here first.

**How to use this**: before merging any change, find the row(s) below matching what you touched,
and open every doc cell listed — confirm it's still accurate, don't assume "I didn't touch the docs
so they're fine." When you add a genuinely new subsystem/topic that doesn't fit an existing row, add
a new row here in the same PR.

| Topic | Source of truth (code) | Docs to check |
|---|---|---|
| **Telegram capture (bot handlers, message → DB row)** | `bot/main.py` | README's "How it works" step 1 and "Usage"; TECH_STACK.md `## 2. Capture` |
| **AI processing (prompt, tool scoping, headless invocation)** | `bot/claude_client.py`, `bot/.claude/settings.json` | README's "How it works" step 2 and Setup; TECH_STACK.md `## 3. Processing`; CLAUDE.md's processing-pipeline section |
| **Database schema / storage** | `bot/db.py`, `dashboard/db.py` | TECH_STACK.md `## 4. Storage`; CLAUDE.md's storage section |
| **Dashboard (routes, templates, search)** | `dashboard/app.py`, `dashboard/templates/*.html` | README's "How it works" step 3; TECH_STACK.md `## 5. Dashboard` |
| **Any visible UI change** (dashboard layout, theme, card fields) | whatever page/component changed | README's Screenshots section (`.github/screenshot-dashboard-*.png` + the `![...]` lines above each) — a stale screenshot is exactly the kind of doc debt this file exists to prevent, same as stale prose |
| **Architecture / request flow** | `bot/main.py`, `bot/claude_client.py`, `dashboard/app.py` (i.e. wherever the actual data path changes) | `docs/architecture.drawio` (+ its exported `.png`/`.svg`/`.gif`); README's "How it works" section that links to it |
| **Docker / Compose / deployment shape** | `docker-compose.yml`, `bot/Dockerfile`, `dashboard/Dockerfile` | README's Setup steps; TECH_STACK.md `## 6. Containerization`; CLAUDE.md's "Running it" |
| **Windows one-click launcher** | `Launch-IdeaVault.ps1` | README's "Windows one-click launcher" callout — especially `$AppUrl` if `DASHBOARD_PORT`'s default ever changes |
| **Configuration (env vars)** | `.env.example` | README's Configuration table |
| **CI/CD** | `.github/workflows/ci.yml`, `.github/dependabot.yml` | TECH_STACK.md `## 7. Dev tooling & CI`; CLAUDE.md's CI/CD section |
| **Development workflow itself** (issue-first, branch/PR/CI-gate/merge) | N/A — process, not code | CLAUDE.md's Development workflow section |
