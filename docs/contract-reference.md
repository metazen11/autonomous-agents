# Contract reference (read on demand)

Long-form material moved out of the rendered global `CLAUDE.md` / host instruction files to keep the
always-loaded prompt small. Rules (MUST / MUST NOT) stay in the rendered file; this holds invocation
examples and reference listings only.

## Code review invocations

Cascade order and fallback triggers are defined in the rendered instructions. Exact calls:

**Tier 1 - Codex CLI** (`codex review`; independent context, good at catching silent no-ops such as an
edit to the wrong config key or a key the framework ignores):
- Post-commit, pre-push: `codex review --base origin/<integration_trunk>`
- Pre-commit, staged work: `codex review --uncommitted`
- Custom focus: pipe instructions via stdin or pass as PROMPT.
- Fall back when: `codex` not on PATH, binary errors, API call fails, usage limit hit.
- Note: codex 0.147 removed `--commit`; do not pass it.

**Tier 2 - Anvil `aa_code_reviewer`** (separate context on the local LLM, schema-validated output, no
cloud dependency or usage limits):

```
mcp__anvil__worktree_run_subagent({
  agent: 'aa_code_reviewer',
  inputs: {
    base_ref:      'origin/dev',
    head_ref:      'HEAD',
    task_title:    '<commit subject>',
    task_body:     '<commit body or one-line summary>',
    changed_files: '<output of: git diff --name-only origin/dev...HEAD>',
  }
})
```

The specialist's canonical contract lives in `~/_CODING/autonomous_agents_mds/agents/` (or an imported
`agent_bundles/*/agents/` source) and renders to each host's synced agents directory; its `Inputs`
section has the full schema. Fall back when the anvil MCP tool is unavailable, the daemon is not
running, or the subagent errors.

**Tier 3 - Claude `aa_code_reviewer` subagent** (last resort; shares the model family but runs in a
fresh context with no in-session memory):

```
Agent({
  subagent_type: 'aa_code_reviewer',
  description:   'Pre-reconcile code review',
  prompt:        'Review the diff between origin/<integration_trunk> and HEAD. Surface blocking issues, simplification opportunities, and DRY violations. Acceptance criteria: <pull from task or commit body>.'
})
```

Output must still be surfaced verbatim to the reconciler; blocking findings still abort the push.

## CTO continuous-improvement agents

- `cto-self-eval` - code health, debt density, maturity scoring
- `cto-arch-review` - service topology, complexity budget, simplification
- `cto-security-posture` - real security vs theater, compliance readiness
- `cto-test-quality` - test meaningfulness, negative tests, coverage gaps
- `cto-dx-review` - onboarding friction, Makefile coverage, error quality
- `cto-dep-health` - supply chain risk, version currency, license audit
- `cto-perf-review` - resource efficiency, query patterns, cost projection
- `cto-parallel-work` - task decomposition, conflict avoidance, isolation

## Dev environment details

- Source of truth: `~/_CODING/` (local SSD, no cloud sync conflicts).
- Backup mirror: `~/Dropbox/_CODING/` (nightly rsync at 8 AM via launchd; backup only, NOT a working copy).
- Sync scripts: `~/_CODING/scripts/sync-bidirectional.sh` (`--to-local`, `--to-dropbox`, `--status`).
- The `~/Dropbox/_CODING/autonomous_agents_mds/` copy is a stale backup pending decommission (track in the autonomous-agents repo).
- Agent hooks source: `~/_CODING/hooks/` (canonical); `~/.claude/hooks/git-session.js` is a symlink to `~/_CODING/hooks/git-session/git-session.js`.
