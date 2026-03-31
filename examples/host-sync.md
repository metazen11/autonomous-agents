# Host Sync Example

Copy and edit environment settings:

```bash
cp .env.example .env
```

Run sync manually:

```bash
python3 scripts/sync_prompt_pack.py print-host-features
python3 scripts/sync_prompt_pack.py check
python3 scripts/sync_prompt_pack.py sync
python3 scripts/sync_prompt_pack.py install-git-hooks
```

What gets synced for the primary hosts:

- Claude: `skill.md`, `agents/*.md`, `CLAUDE.md`, optional settings snippet
- Codex: `skill.md`, `agents/*.md`, `AGENTS.md`, optional TOML/MCP snippet
- Gemini: `skill.md`, `agents/*.md`, `GEMINI.md`, optional MCP snippet

Recommended `.env` fields for the three main hosts:

```dotenv
CLAUDE_SKILL_PATH=~/.claude/skills/autonomous/skill.md
CLAUDE_AGENTS_DIR=~/.claude/agents
CLAUDE_INSTRUCTIONS_PATH=~/.claude/CLAUDE.md
CLAUDE_CONFIG_SNIPPET_PATH=~/.claude/autonomous-settings.snippet.json

CODEX_SKILL_PATH=~/.codex/skills/autonomous/skill.md
CODEX_AGENTS_DIR=~/.codex/agents
CODEX_INSTRUCTIONS_PATH=~/.codex/AGENTS.md
CODEX_CONFIG_SNIPPET_PATH=~/.codex/autonomous.toml

GEMINI_SKILL_PATH=~/.gemini/skills/autonomous/skill.md
GEMINI_AGENTS_DIR=~/.gemini/agents
GEMINI_INSTRUCTIONS_PATH=~/.gemini/GEMINI.md
GEMINI_CONFIG_SNIPPET_PATH=~/.gemini/autonomous.mcp_config.json
```

Optional platform scheduling:

```bash
python3 scripts/sync_prompt_pack.py write-launchd
python3 scripts/sync_prompt_pack.py write-windows-xml
```

Recommended behavior:

- use git hooks first
- use scheduler output as a backup
- keep this repo as the single source of truth
