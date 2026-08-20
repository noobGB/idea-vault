FROM python:3.14-slim

# Node.js is needed for the Claude Code CLI (npm package) -- claude_client.py
# shells out to it as a subprocess to do the actual AI processing.
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Includes .claude/settings.json (tool-permission scoping -- see claude_client.py)
COPY . .

CMD ["python", "main.py"]
