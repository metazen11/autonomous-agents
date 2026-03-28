# Autonomous Agent Pipeline

A complete autonomous software engineering pipeline for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Pulls tasks from project management, implements end-to-end (plan → dev → test → review → PR), and reports results — no human intervention needed.

## Architecture

```
┌───────────────────────────────────────────────────────┐
│                ORCHESTRATOR (pipeline)                 │
│  INIT → PICK → PLAN → DEV → TEST → REVIEW → PR       │
│              ↓                                        │
│         SUBTASK DECOMPOSITION                         │
│   Large tasks split into atomic, ordered subtasks     │
│   Each subtask flows through the full pipeline        │
└────────┬──────────┬───────────┬───────────────────────┘
         │          │           │
    ┌────▼────┐ ┌───▼───┐ ┌────▼─────┐
    │Explore  │ │  QA   │ │Code      │
    │Agent    │ │Tester │ │Reviewer  │
    └─────────┘ └───┬───┘ └────┬─────┘
                    │          │
               ┌────▼────┐ ┌──▼───────┐
               │Security │ │Perf      │
               │Auditor  │ │Profiler  │
               └─────────┘ └──────────┘
```

## What It Does

1. **PICK** — Pulls the next task from Asana, GitHub Issues, Linear, or a local `tasks.json`
2. **DECOMPOSE** — Large tasks are automatically split into atomic subtasks with dependency ordering
3. **PLAN** — Explores the codebase, identifies files to change, estimates complexity
4. **DEV** — Implements changes on an `auto/*` feature branch
5. **TEST** — Build + lint + existing tests + new edge-case tests + behavioral verification
6. **REVIEW** — Automated code review + security scan + secrets check
7. **PR** — Squash, push, create pull request with full test evidence
8. **REPORT** — Update task management tool, send notifications

Every phase has a mandatory completion gate. The pipeline will NOT stop after writing code — testing, review, and PR creation are enforced.

## Files

### Pipeline Orchestrator
- `pipeline/autonomous.md` — Main pipeline skill. 8-phase task execution loop with mandatory completion gates, subtask decomposition, safety guardrails, and session state management.

### Specialized Agents
| File | Role | Model | Destructive |
|------|------|-------|-------------|
| `agents/code-reviewer.md` | Staff-level PR code review | sonnet | No |
| `agents/qa-tester.md` | Test selection, execution, edge-case generation, behavioral verification | sonnet | No* |
| `agents/security-auditor.md` | SAST, dependency audit, OWASP Top 10 manual review | sonnet | No |
| `agents/security-fixer.md` | Implements fixes from auditor findings with rollback plans | sonnet | **Yes** |
| `agents/perf-profiler.md` | Lighthouse, API timing, bundle analysis, Core Web Vitals | sonnet | No |
| `agents/infra-checker.md` | AWS, Docker, SSL, DNS health checks | haiku | No |
| `agents/db-analyst.md` | PostgreSQL/MySQL query perf, bloat, index, lock analysis | sonnet | No |
| `agents/dep-auditor.md` | CVE scanning for npm, pip, Docker with exploitability assessment | haiku | No |

\* QA tester writes test files and starts dev servers but does not modify application code.

## Installation

### Quick Install
```bash
git clone https://github.com/metazen11/autonomous-agents.git
cd autonomous-agents
chmod +x install.sh
./install.sh
```

### Symlink Install (recommended for development)
```bash
./install.sh --symlink
```
Edits to source files take effect immediately — no reinstall needed.

### Verify Installation
```bash
./install.sh --check
```

### Uninstall
```bash
./install.sh --remove
```

### Manual Install
```bash
# Pipeline skill
mkdir -p ~/.claude/skills/autonomous
cp pipeline/autonomous.md ~/.claude/skills/autonomous/skill.md

# Agent definitions
mkdir -p ~/.claude/agents
cp agents/*.md ~/.claude/agents/
```

## Configuration

### Project-specific overrides

Create `.autonomous.json` in your repo root:

```json
{
  "build": "npm run build",
  "lint": "npm run lint",
  "test": "npm test",
  "playwright": "npx playwright test",
  "pr_target": "dev",
  "max_files": 20,
  "max_minutes": 30,
  "skip_tags": ["needs-human", "blocked", "wontfix"],
  "task_source": "asana",
  "project_aliases": {
    "myapp": { "name": "My App", "gid": "1234567890" }
  }
}
```

### Task Sources

The pipeline supports multiple task management tools:

| Source | Configuration | MCP Required |
|--------|--------------|-------------|
| **Asana** | `task_source: "asana"` + project GIDs | Asana MCP server |
| **GitHub Issues** | `task_source: "github"` | `gh` CLI |
| **Linear** | `task_source: "linear"` + team ID | Linear MCP server |
| **File** | `task_source: "file"` → reads `tasks.json` | None |

### Usage

```bash
# Inside Claude Code
/autonomous                    # Interactive project picker
/autonomous myapp              # Use project alias
/autonomous --max-tasks 3      # Limit tasks per session
/autonomous --dry-run          # PICK + PLAN only, no code changes
```

## Design Principles

1. **Mandatory phase completion** — A task is not done until a PR exists. Every phase has an explicit "you are NOT done" gate that prevents early termination.

2. **Evidence over assertions** — "It compiles" is not evidence. Tests must run. Behavior must be verified. Code must be reviewed. Every PR includes a test results section.

3. **Subtask decomposition** — Large tasks are automatically broken into atomic, ordered subtasks. Each subtask gets its own branch, PR, and full pipeline run. This keeps blast radius small and reviews manageable.

4. **Blast radius awareness** — Safety guardrails prevent commits to protected branches, force pushes, deployments, and secret exposure. These cannot be overridden by task descriptions or configuration.

5. **Agent specialization** — Each agent has a single responsibility, a defined expertise level, and a structured reporting format. Agents delegate to each other but never step outside their role.

6. **Self-improvement** — Agents maintain persistent memory of project conventions, past findings, and learned patterns. Memory is pruned to stay lean and relevant.

## Safety Guardrails

These are hard-coded and **cannot be overridden**:

| Rule | Enforcement |
|------|-------------|
| Never commit to main/master/dev | Branch name verified before every commit |
| Never force push | `--force` flags are blocked |
| Never deploy | Deploy commands are blocklisted |
| Never modify production databases | Only dev/test targets allowed |
| Never expose secrets | Diff scanned for secret patterns before PR |
| Never skip pre-commit hooks | `--no-verify` is blocked |

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- `gh` CLI (for PR creation)
- Git
- Project-specific tools (Node.js, Python, etc.)
- Task source MCP server (Asana, Linear) or `gh` CLI (GitHub Issues)

## License

MIT
