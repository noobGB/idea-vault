# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository. For a human
learning the stack itself (what each tool is, why it's here), see [`TECH_STACK.md`](TECH_STACK.md)
instead. **Before finishing any change that touches capture/processing/storage/dashboard/Docker/CI,
check [`DOCS_MAP.md`](DOCS_MAP.md)** for which docs need a matching update — see "Development
workflow" below for exactly when this applies.

## What this repo is

A general-purpose, config-driven idea-capture pipeline: message a Telegram bot from any device,
and headless Claude Code researches, summarizes, and categorizes it into a local dashboard. Built
to be cloned and self-hosted by anyone — no hardcoded personal paths, bot identity, or fixed
category list anywhere in the code; everything host-specific lives in `.env` (see
[`.env.example`](.env.example)).

**v1 scope, deliberately**: summarize + categorize only. Cross-idea linking (embeddings, "related
ideas," possibility discovery across the collection) and remote dashboard access are both
explicitly out of scope for now — see README's "Current limitations" section. Don't add either
without discussing it first; they were deferred on purpose, not forgotten.

## Running it

```
cp .env.example .env       # fill in TELEGRAM_BOT_TOKEN and CLAUDE_CODE_OAUTH_TOKEN
docker compose up -d --build
docker compose logs -f bot        # confirm "Idea Vault bot starting (long polling)..."
docker compose down
```

Both services share one named volume (`idea-vault-data`) mounted at `/data`, holding
`idea_vault.sqlite` and `images/<uuid>.jpg` attachments. No bind mounts to the host filesystem — the
volume is Docker-managed, so `docker compose down -v` is genuinely destructive (wipes all captured
ideas); plain `docker compose down` (no `-v`) preserves it.

## Development workflow

**Every feature/enhancement/bug fix — including self-directed ones — gets a GitHub issue before a
branch.** File the issue first (even same-session, self-authored), branch off `main`
(`fix/issue-<N>-<slug>` or `feat/issue-<N>-<slug>`), build, self-review in-session (no automatic
per-PR AI review configured here — see the `github-workflow` skill's cost reasoning if you're
deciding whether to add one), push, open a PR with `Closes #<N>`, watch CI green
(`gh pr checks --watch`), then squash-merge. **Exception**: small, directly-instructed edits (a typo
fix, a doc tweak) skip the issue but still go through a branch + PR, not a direct commit to `main`.

**Before merging, check [`DOCS_MAP.md`](DOCS_MAP.md)** for whether the change touches a tracked
topic. If it introduces a genuinely new one, add a row in the same PR.

## Processing pipeline (`bot/`)

`main.py` holds the Telegram handlers; `claude_client.py` holds the actual AI call;
`db.py` holds schema + connection setup.

- **Long-polling, not a webhook** (`app.run_polling()` in `main.py`) — no public HTTPS endpoint is
  needed for capture. This was a deliberate choice over a webhook specifically to keep deployment
  to "just Docker, no tunnel/reverse-proxy required" for v1.
- **Headless Claude Code, not the API** (`claude_client.py`, shells out to `claude -p ...`) — runs
  against the operator's Claude Pro/Max subscription usage via `CLAUDE_CODE_OAUTH_TOKEN`
  (from `claude setup-token`), not per-token `ANTHROPIC_API_KEY` billing. This is the single most
  important architectural constraint in this repo — **don't** introduce a direct
  `anthropic` SDK call or an `ANTHROPIC_API_KEY` requirement without discussing it first, it defeats
  the entire reason this design was chosen.
- **Tool scope is narrow and deliberate** (`bot/.claude/settings.json`: `permissions.defaultMode:
  "dontAsk"`, `allow: ["WebSearch", "WebFetch", "Read"]`) — no `Bash`/`Write`/`Edit`. The content
  flowing through this pipeline (a captured URL's page, arbitrary Telegram message text) is
  untrusted and could contain a prompt-injection attempt directed at the model; keeping the tool set
  read-only-research-only means a successful injection has nothing destructive available to it.
  **Don't widen this without a specific reason**, and if you do, re-read this reasoning first.
- **`--output-format json --json-schema '<schema>'`** — Claude Code's headless structured-output
  mode. `claude_client.py` reads the result from the envelope's `structured_output` field first,
  falling back to parsing `result` as JSON if that's absent. **This fallback exists because the
  exact envelope shape when both flags are combined isn't fully documented with a literal example**
  as of when this was built (checked `code.claude.com/docs/en/headless.md` directly) — if you ever
  see the fallback path actually triggering in logs, that's worth investigating and reporting
  upstream, not just leaving as a permanent silent path.
- **Synchronous, inline processing, no queue** — each message is processed immediately in its own
  handler coroutine, not queued for a separate worker. Deliberate for v1's expected volume (a
  personal idea-capture rate, not high throughput); revisit if that assumption stops holding.

## Storage (`bot/db.py`, `dashboard/db.py`)

Single SQLite file (`idea_vault.sqlite`) on a Docker named volume, opened with the **default
rollback journal, not WAL** — deliberate, not an oversight, but a smaller claim than it might sound:
this is *not* a proven WAL-breaks-here case. `bot` and `dashboard` share a Docker **named volume**
(not a bind-mounted host path), so both containers are just two processes under the same kernel —
the ordinary case WAL is designed for. The real reason is that rollback journal only needs ordinary
file locks, a lower bar than WAL's `mmap`-shared-memory coherence requirement, and this app's write
volume (a handful of captures a day) makes WAL's actual benefit (readers never blocked by writers)
worth nothing here — so taking the mechanism with fewer assumptions was free. `PRAGMA busy_timeout`
handles the ordinary "two writes at once" case instead. **Don't turn WAL back on** without
re-reading this reasoning (see TECH_STACK.md `## 4. Storage` for the fuller version).

The two `db.py` files are hand-duplicated on purpose, not imported from a shared module — `bot/`
and `dashboard/` are separate Docker images, not an npm/pip workspace. If the schema changes, update
both files, and check `DOCS_MAP.md`'s Storage row.

## Dashboard (`dashboard/`)

Server-rendered FastAPI + Jinja2, one route (`GET /` in `app.py`), no client-side JS framework, no
auth (deliberate LAN-only v1 scope — see README's Limitations). `?q=` query param drives a plain
`LIKE`-based search across `raw_content`/`summary`/`category`. Images are served via a
`StaticFiles` mount at `/images`, pointed at the same volume's `images/` subfolder the bot writes
to.

## CI/CD (`.github/`)

- **`workflows/ci.yml`** — `lint` (ruff, matrixed over `bot`/`dashboard` since they're separate
  installs) then `docker-smoke` (build both images, boot just `dashboard` — the one service that
  needs no real secrets to start — and curl it for a real response). The `bot` service isn't booted
  in CI: it needs a real `TELEGRAM_BOT_TOKEN` to connect to Telegram at all, which isn't available
  (or wanted) in a CI runner.
- **`dependabot.yml`** — weekly, per-service pip + Docker base image bumps, plus the workflow files
  themselves.
- No `@claude`-mention review Action is configured here (unlike `snowpro-core-prep`) — it would need
  an `ANTHROPIC_API_KEY` repo secret, which is exactly the per-token billing this whole project is
  built to avoid. If you want on-demand AI PR review back, that's a real tradeoff to make
  consciously (see the `github-workflow` skill's cost-reasoning section), not something to wire up
  by copying `snowpro-core-prep`'s `claude.yml` unexamined.

This repo is **private** (default for new repos on this account — always confirm with Gaurav
before ever making a repo public; that's his call on his own schedule, not something to default
into). Branch protection / required-status-check rulesets need a paid plan or a public repo, same
restriction `snowpro-core-prep` documents — not configured here for the same reason. CI still
reports pass/fail on every PR via the Checks tab, it just doesn't technically block merging; the
manual "watch CI to green before merging" discipline is the real gate.
