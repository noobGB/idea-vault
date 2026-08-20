# Tech Stack — What Each Piece Does, and Why

This file is for humans learning the stack, not for an AI coding agent working in the repo (that's
[`CLAUDE.md`](CLAUDE.md)). This file assumes you know how to code but maybe not this particular set
of tools, and maps each one to the actual line of code using it — not a generic tutorial.

Organized in the order an idea actually flows through the system: a Telegram message → a database
row → an AI processing step → a browser dashboard.

## 1. Language & runtime

**Python 3.12**, no framework beyond what each service needs individually. Chosen over Node/TS
(the stack used in this author's other projects) because `python-telegram-bot` is the most mature
Telegram bot library available, and the two services here are small enough that a shared-workspace
concern (the reason the other project uses TypeScript throughout) doesn't apply — `bot/` and
`dashboard/` are two independent processes that never import each other's code.

## 2. Capture — `python-telegram-bot`

**`python-telegram-bot`** (`bot/main.py`) — a Python wrapper around Telegram's Bot API. This app
uses **long-polling** (`app.run_polling()`), not a webhook: the bot repeatedly asks Telegram "any
new messages for me?" over an outbound connection it initiates, rather than Telegram pushing to an
inbound URL you'd have to expose publicly. That means **no public HTTPS endpoint is needed at all**
for capture to work — the whole bot service can run behind a home NAT with zero port-forwarding,
which is exactly why Telegram was chosen as the capture channel over a custom app (a share-target
PWA would need real hosting; email-to-self would need SMTP/IMAP wiring for roughly the same
frictionless result Telegram gives for free).

`MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)` and
`MessageHandler(filters.PHOTO, handle_photo)` (`bot/main.py`) are the two entry points — everything
you send is one of these two shapes.

## 3. Processing — headless Claude Code, not the Claude API

**The Claude Code CLI, in headless/print mode** (`claude -p ...`, invoked as a subprocess from
`bot/claude_client.py`) is the actual "AI" in this project — not a direct call to Anthropic's
Messages API. This is a deliberate choice: Claude Code CLI usage run this way counts against a
Claude Pro/Max **subscription's** included usage, not per-token API billing, and its `-p` mode is
an officially supported scripting/automation path (not a hack) — see
[`code.claude.com/docs/en/headless.md`](https://code.claude.com/docs/en/headless.md) and
[`.../docs/en/costs.md`](https://code.claude.com/docs/en/costs.md). `claude setup-token` (run once,
by hand, during setup — see README) generates the long-lived OAuth token that authenticates every
subsequent headless call, so nothing here needs an `ANTHROPIC_API_KEY`.

- **`--output-format json --json-schema '<schema>'`** — asks Claude Code to return a
  schema-conforming structured object (`{"summary": ..., "category": ...}`) instead of free text,
  so `claude_client.py` can parse it directly rather than regexing a prose reply.
- **`--allowedTools`/`.claude/settings.json`** (`bot/.claude/settings.json`) — scopes what tools the
  headless run may use. Set to exactly `WebSearch`, `WebFetch`, `Read` — deliberately **excluding**
  `Bash`, `Write`, and `Edit`. The content this pipeline processes is untrusted (a captured URL's
  page, or arbitrary message text) and could contain a prompt-injection attempt aimed at the model;
  narrowing the tool set to read-only research tools means even a successful injection has nothing
  destructive to reach for. See `bot/claude_client.py`'s module docstring for the full reasoning.
- **`WebSearch`/`WebFetch`** are what let the model actually research a captured link or topic
  rather than just restating the raw text back at you.
- **`Read`** is what lets it look at a captured screenshot — the prompt points it at the saved
  image file's path on disk (both the bot process and the `claude` subprocess run inside the same
  container, sharing the same mounted volume, so no file-transfer step is needed).

## 4. Storage — SQLite, deliberately not WAL mode

**`sqlite3`** (Python's standard-library driver, `bot/db.py` and `dashboard/db.py`) — one file,
`idea_vault.sqlite`, on a Docker named volume shared by both containers. Opened with the **default
rollback journal**, not `journal_mode = WAL`. The two modes need different guarantees to stay
correct: rollback journal only needs ordinary POSIX file locks (`fcntl`) on the main file — the
same low-level guarantee any two processes sharing a file already need. WAL needs more: every
connection `mmap()`s a `-shm` file into its own memory and relies on that shared mapping staying
byte-coherent across processes, which is what SQLite's own docs say breaks down over an actual
network filesystem.

**Worth being precise about what this project's own deployment shape actually proves, versus what
it doesn't.** `bot` and `dashboard` share a Docker **named volume**, not a bind-mounted host path —
a named volume lives inside Docker's own storage, so both containers are just two processes under
the same kernel, the ordinary case WAL is designed for and would likely work fine. The stronger risk
(one process reaching a file through Docker Desktop's bind-mount translation while a *different*,
native host process reaches the identical path directly — two genuinely different filesystem
stacks) is real, but it's the shape of a *different* project in this author's workspace (a
Home Assistant stack with a bind mount), not this one. Nothing here has actually been proven to
break under WAL.

So the honest reason for skipping WAL is smaller than "it would break": rollback journal's
correctness depends on strictly less (file locking only, no `mmap`-coherence assumption), and this
app's write volume — a handful of captures a day — means WAL's actual benefit (readers never
blocked by writers) is worth nothing in practice. Given that, taking the mechanism with fewer
assumptions cost nothing. `PRAGMA busy_timeout` is set regardless, so a write from one container
waits briefly for the other's lock to clear rather than failing immediately.

`bot/db.py` and `dashboard/db.py` are near-identical, **hand-duplicated on purpose** — the two
services are separate Docker images, not a shared package, so duplicating a ~15-line schema
definition was simpler than adding a shared library for that alone.

## 5. Dashboard — FastAPI + Jinja2, server-rendered

**FastAPI** (`dashboard/app.py`) — a small Python web framework, chosen here purely for its
built-in Jinja2/`StaticFiles` integration and low ceremony; there's exactly one route (`GET /`).
**Jinja2** (`dashboard/templates/*.html`) renders the page server-side — no client-side JS
framework, because there's no interactivity beyond a search box (a plain HTML `<form method="get">`
that reloads the page with a `?q=` query param, handled directly in `app.py`'s `index()`). **No
authentication** is implemented anywhere in the dashboard — deliberate for a v1 scoped to LAN/
desktop access only (see README's Limitations section); don't expose this port to the open internet
without adding your own auth layer first.

**`uvicorn`** is the ASGI server that actually runs the FastAPI app inside the container
(`dashboard/Dockerfile`'s `CMD`).

## 6. Containerization — Docker, Docker Compose

**Two services, one Compose file** (`docker-compose.yml`) — `bot` and `dashboard` — sharing one
named volume (`idea-vault-data`, mounted at `/data` in both) that holds the SQLite file and
captured image attachments. One compose file per logical stack (not one per container) is a
deliberate convention: it puts every service on the same Compose-created network with automatic
DNS-by-service-name, and keeps `docker compose up`/`down` scoped to the whole feature at once.

**`bot/Dockerfile`** additionally installs Node.js and `npm install -g @anthropic-ai/claude-code`
on top of the Python base image — the Claude Code CLI is a Node package, needed alongside Python
purely so `claude_client.py` has something to `subprocess` out to.

## 7. Dev tooling & CI

**`ruff`** — a fast Python linter, run in CI (`.github/workflows/ci.yml`) against both `bot/` and
`dashboard/` independently (they're separate images, not a shared package, same reasoning as the
duplicated `db.py` above).

**GitHub Actions** — `ci.yml` runs lint (both services) then a Docker smoke test: build both
images, boot just the `dashboard` service (the one with no external secrets required to start), and
curl it for a real response — the closest thing this repo has to an integration test.

**Dependabot** (`.github/dependabot.yml`) — weekly PRs for each service's pip dependencies, each
service's Docker base image, and the workflow files themselves.

---

For how these pieces fit together architecturally (file layout, data flow, known gotchas), see
[`CLAUDE.md`](CLAUDE.md). For how to actually run this, see [`README.md`](README.md).
