# Specialist Contracts

Prompt files live under `agents/`.

Runtime-side specialist contracts live in:

- `autonomous_pipeline/specialists.py`

These contracts define:

- read-only versus bounded-write behavior
- required inputs
- optional inputs
- expected output keys
- escalation conditions

Current core specialists:

- `code-reviewer`
- `qa-tester`
- `security-auditor`
- `security-fixer`
- `dep-auditor`
- `db-analyst`
- `perf-profiler`
- `infra-checker`
- `soc2-auditor`
- `hipaa-auditor`
- `compliance-fixer`
- `skill-promoter`

## Cross-Host Reuse

Agent definitions are reusable across Claude, Codex, Gemini, Anvil, and future hosts when they are treated as contracts rather than host-specific command snippets.

Canonical sources:

- First-party agents: `agents/*.md`
- Imported/curated bundles: `agent_bundles/*/agents/*.md`
- Runtime contract metadata: `autonomous_pipeline/specialists.py`
- Sync/render logic: `autonomous_pipeline/host_sync.py` and `scripts/sync_prompt_pack.py`

Runtime install directories are not canonical. Do not copy from `~/.claude/agents`, `~/.codex/agents`, `/opt/anvil/agents`, or project-local generated copies into another host. Import useful host-local agents into `agent_bundles/` or graduate them into first-party `agents/`, then render them through the sync tool.

Portable agent contract fields:

- role and responsibility
- required inputs
- output schema
- read/write boundary
- review criteria and blocking findings
- quality gates and verification evidence
- escalation rules

Host-specific adapter fields:

- invocation syntax, such as Claude `Agent(...)`, Codex CLI or multi-agent tools, Anvil MCP calls, or Gemini activation
- memory API calls
- worktree/subagent dispatch mechanics
- host-local config paths
