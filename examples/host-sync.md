# Host Sync Example

Copy and edit environment settings:

```bash
cp .env.example .env
```

Run sync manually:

```bash
python3 scripts/sync_prompt_pack.py print-host-features
python3 scripts/sync_prompt_pack.py update-and-sync --repo-root ~/_CODING/autonomous_agents_mds
python3 scripts/sync_prompt_pack.py check
python3 scripts/sync_prompt_pack.py install-git-hooks
```

What gets synced for the primary hosts:

- Claude: `skill.md`, `agents/*.md`, `CLAUDE.md`, optional settings snippet
- Codex: `skill.md`, `agents/*.md`, `AGENTS.md`, optional TOML/MCP snippet
- Gemini: `skill.md`, `agents/*.md`, `GEMINI.md`, optional MCP snippet
- Anvil: pipeline prompt, core agents, curated agent bundles, schemas, scripts, `AGENTS.md`

The GitHub repo is the distribution source:

```text
https://github.com/metazen11/autonomous-agents.git
```

Use `agents/` for first-party agents and `agent_bundles/<bundle>/agents/` for
curated marketplace/plugin agents that should be available across hosts. The
financial-services marketplace agents live in
`agent_bundles/financial-services/agents/` and are copied verbatim from the
Claude marketplace source.

Before pushing a sync into host installs, reconcile inventories:

```bash
PYTHONPATH=. python3 scripts/sync_prompt_pack.py reconcile-agents \
  --agent-dir /Users/mz/_CODING/anvil/agents \
  --agent-dir /opt/anvil/agents
```

Use the report as the merge checklist:

- `missing_from_repo` means a host has an agent not yet tracked centrally.
- `missing_from_target` means a host will receive a central agent on sync.
- `diverged` means both sides have an agent with the same canonical `aa_` name
  but different content.
- `target_newer` and `repo_newer` use file modification time as a hint only;
  inspect the diff before importing or overwriting.

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

- use `update-and-sync` in scheduled jobs
- use launchd, cron, or Windows Task Scheduler only as OS-specific wrappers
- keep the GitHub repo as the distribution source and the local checkout as an install cache

Fast setup on another Mac:

```bash
mkdir -p ~/_CODING
git clone https://github.com/metazen11/autonomous-agents.git ~/_CODING/autonomous_agents_mds
cd ~/_CODING/autonomous_agents_mds
cp .env.example .env
python3 scripts/sync_prompt_pack.py update-and-sync --repo-root "$PWD"
```

If `.env` already exists on that Mac, future updates are just:

```bash
cd ~/_CODING/autonomous_agents_mds
python3 scripts/sync_prompt_pack.py update-and-sync --repo-root "$PWD"
```
