# Idea Vault

A single place to dump every idea, link, or screenshot that crosses your mind — from your phone or
your desktop — and let an AI file it away for you: researched, summarized, and categorized, with
zero manual sorting.

For how each piece of the stack works and why, see [`TECH_STACK.md`](TECH_STACK.md). For
architecture/gotchas aimed at an AI coding agent working on this repo, see [`CLAUDE.md`](CLAUDE.md).

## How it works

1. **Capture** — message a Telegram bot (text, a link, or a photo/screenshot). Works identically
   from mobile or desktop, no app to install beyond Telegram itself.
2. **Process** — the bot researches the idea (web search/fetch for links, or a quick look at an
   image) via headless Claude Code, then writes a short summary and assigns a category, reusing an
   existing category when it fits.
3. **Browse** — a local web dashboard shows everything grouped by category, with search.

```
Telegram (you) --> bot service --> claude -p (headless) --> SQLite --> dashboard service --> you, in a browser
```

## Setup

**Prerequisites**

- Docker + Docker Compose
- A Telegram account
- A **Claude Pro or Max subscription** (this project deliberately does *not* use the pay-per-token
  Claude API — see [`CLAUDE.md`](CLAUDE.md) for why)
- The Claude Code CLI installed somewhere you can run `claude setup-token` once (your own machine
  is fine, even if that's not where you'll run this stack)

**Steps**

1. Create your own bot: message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
   follow the prompts. You'll get a token like `123456789:AAExampleTokenHere`.
2. Generate a long-lived OAuth token for headless automation, tied to your subscription:
   ```
   claude setup-token
   ```
3. Clone this repo, then:
   ```
   cp .env.example .env
   ```
   and fill in `TELEGRAM_BOT_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN` from the two steps above.
4. Build and start:
   ```
   docker compose up -d --build
   ```
5. Message your bot on Telegram — send it a plain thought, a link, or a photo. It'll reply once
   processed.
6. Open `http://localhost:8090` (or whatever `DASHBOARD_PORT` you set) to browse everything you've
   captured, grouped by category, searchable.

## Configuration

All configuration is environment variables, set in `.env` (see [`.env.example`](.env.example) for
the full list with instructions on obtaining each value):

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Your bot's token from @BotFather |
| `CLAUDE_CODE_OAUTH_TOKEN` | yes | Long-lived token from `claude setup-token`, authorizes headless processing against your subscription |
| `DASHBOARD_PORT` | no (default `8090`) | Host port the dashboard is published on |

No category list, bot identity, or file paths are hardcoded anywhere in the code — every
deployment starts empty and learns its own categories from whatever you actually capture.

## Current limitations (v1)

- **Dashboard is LAN/desktop-only** — no built-in remote access. If you want it reachable away
  from home, put it behind your own tunnel (e.g. a Cloudflare Tunnel) or reverse proxy.
- **No cross-idea linking yet** — each idea is summarized and categorized independently; surfacing
  related ideas or "possibilities" across your collection is planned for a later version, once
  there's enough volume for it to be meaningful.
- **No auth on the dashboard** — by design, for a LAN-only v1. Don't expose it to the open internet
  without adding your own auth layer first.

## License

MIT — see [`LICENSE`](LICENSE). Use it, fork it, change it.
