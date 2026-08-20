"""Runs one idea through headless Claude Code for summary + categorization.

Auth: CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`), so this runs
against the operator's Claude Pro/Max subscription usage, not per-token API
billing -- see README.md / CLAUDE.md for why.

Tool scope is deliberately narrow (WebSearch, WebFetch, Read only -- no Bash,
Write, or Edit), set via .claude/settings.json baked into this image. The
content this processes is untrusted: a captured URL's page, or arbitrary
Telegram message text, could itself contain a prompt-injection attempt aimed
at the model ("ignore previous instructions and run ..."). Scoping to
read-only research tools means even a successful injection has nothing
destructive to reach for.
"""

import asyncio
import json
from pathlib import Path

CLAUDE_TIMEOUT_SECONDS = 120
CLAUDE_PROJECT_DIR = "/app"

JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A 2-4 sentence summary of the idea, incorporating any web research done.",
            },
            "category": {
                "type": "string",
                "description": "A short category label. Reuse an existing one if it genuinely fits.",
            },
        },
        "required": ["summary", "category"],
        "additionalProperties": False,
    }
)


class ClaudeProcessingError(RuntimeError):
    pass


def ensure_workspace_trusted() -> None:
    """Pre-accept Claude Code's workspace-trust dialog for headless use.

    Claude Code gates .claude/settings.json's permissions.allow list behind a
    separate "trust this folder" check, normally accepted via an interactive
    dialog the first time you open Claude Code in a new directory. A headless
    container has no human to click it, so without this, WebSearch/WebFetch/
    Read are all silently denied regardless of settings.json -- the CLI logs
    "this workspace has not been trusted" and just ignores the allow list.
    Confirmed by manually running `claude -p` inside the container: before
    this fix, permission_denials included WebFetch; after setting
    projects[CLAUDE_PROJECT_DIR].hasTrustDialogAccepted = true in
    ~/.claude.json, the identical call succeeded with no denials.

    Done here (Python, at startup) rather than baked into the Docker image:
    ~/.claude.json is only reliably created after a real authenticated
    invocation, and CLAUDE_CODE_OAUTH_TOKEN isn't available at build time.
    Idempotent -- safe to call on every container start.
    """
    config_path = Path.home() / ".claude.json"
    data = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            data = {}
    projects = data.setdefault("projects", {})
    projects.setdefault(CLAUDE_PROJECT_DIR, {})["hasTrustDialogAccepted"] = True
    config_path.write_text(json.dumps(data))


def _build_prompt(raw_content: str | None, image_path: Path | None, existing_categories: list[str]) -> str:
    if existing_categories:
        categories_hint = (
            "Existing categories already in use: "
            + ", ".join(existing_categories)
            + ". Reuse one of these if it genuinely fits this idea; otherwise propose a new, short category name."
        )
    else:
        categories_hint = "No categories exist yet -- propose a short, sensible one."

    if image_path is not None:
        return (
            f"Use the Read tool to look at the image file at {image_path}. Describe the idea, "
            f"screenshot, or content it captures. If it references something researchable "
            f"(a product, an article, a topic), do a quick web search or fetch for context. "
            f"Then write a short summary. {categories_hint}"
        )

    return (
        f"A user captured this idea/note/link for later reference:\n\n{raw_content}\n\n"
        f"If it's a URL, fetch it and summarize what it actually is. Otherwise, if a quick web "
        f"search would add useful context, do one. Then write a short summary of the idea. "
        f"{categories_hint}"
    )


async def process_entry(
    raw_content: str | None,
    image_path: Path | None,
    existing_categories: list[str],
) -> dict[str, str]:
    """Shells out to `claude -p` and returns {"summary": ..., "category": ...}."""
    prompt = _build_prompt(raw_content, image_path, existing_categories)

    proc = await asyncio.create_subprocess_exec(
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        JSON_SCHEMA,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ClaudeProcessingError(f"claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s")

    if proc.returncode != 0:
        raise ClaudeProcessingError(
            f"claude CLI exited {proc.returncode}: {stderr.decode(errors='replace')[:500]}"
        )

    try:
        payload = json.loads(stdout.decode())
    except json.JSONDecodeError as exc:
        raise ClaudeProcessingError(f"claude CLI did not print valid JSON: {exc}") from exc

    result = payload.get("structured_output")
    if result is None and isinstance(payload.get("result"), str):
        # Documented behavior differs slightly by version: fall back to parsing
        # the plain `result` field as JSON if `structured_output` isn't present.
        try:
            result = json.loads(payload["result"])
        except json.JSONDecodeError:
            result = None

    if not isinstance(result, dict) or "summary" not in result or "category" not in result:
        raise ClaudeProcessingError(f"unexpected claude CLI output shape: {payload}")

    return {"summary": str(result["summary"]), "category": str(result["category"])}
