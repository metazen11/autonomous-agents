# Autonomous Agents

Host-agnostic prompt pack and local Python runtime for autonomous software delivery.

This repository currently provides:

- a shared orchestration policy for `INIT -> PICK -> PLAN -> DEV -> CODE_REVIEW -> TEST -> REVIEW -> PR -> REPORT -> IMPROVE`
- specialist agent contracts under [agents/](agents)
- a runnable local Python runtime under [autonomous_pipeline/](autonomous_pipeline)
- task adapters for `todo.json` and GitHub Issues
- durable learning through `agentMemory`
- host sync tooling for Claude, Codex, and Gemini

This repository is not yet a fully self-driving production orchestrator. The verified path today is a local-first runtime with real task pickup, artifacts, review/test flow, and host-native prompt-pack sync.

## Start Here

- [docs/system-overview.md](docs/system-overview.md)
- [docs/architectural-overview.md](docs/architectural-overview.md)
- [docs/host-integration.md](docs/host-integration.md)
- [examples/README.md](examples/README.md)

## Current Architecture

There are four layers:

1. Prompt pack
2. Local runtime
3. Durable memory
4. Host integration

Prompt pack:

- [pipeline/autonomous.md](pipeline/autonomous.md)
- [agents/AGENT_AGNOSTIC_GUIDE.md](agents/AGENT_AGNOSTIC_GUIDE.md)
- [agents/code-reviewer.md](agents/code-reviewer.md) and the rest of [agents/](agents)

Local runtime:

- [scripts/run_pipeline.py](scripts/run_pipeline.py)
- [autonomous_pipeline/runner.py](autonomous_pipeline/runner.py)
- [autonomous_pipeline/adapters/](autonomous_pipeline/adapters)
- [autonomous_pipeline/specialists.py](autonomous_pipeline/specialists.py)
- [autonomous_pipeline/verification.py](autonomous_pipeline/verification.py)

Durable memory:

- [docs/agent-memory.md](docs/agent-memory.md)
- [autonomous_pipeline/memory/](autonomous_pipeline/memory)
- [scripts/validate_agent_memory.py](scripts/validate_agent_memory.py)

Host integration:

- [scripts/sync_prompt_pack.py](scripts/sync_prompt_pack.py)
- [autonomous_pipeline/host_sync.py](autonomous_pipeline/host_sync.py)
- generated host entrypoints such as `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`

## What Works Today

- canonical task model and run-state model
- `todo.json` adapter for local/offline execution
- GitHub Issues adapter for shared backlog execution
- resumable local run state in `.autonomous-state.json`
- artifact capture in `.runs/` or configured artifact directories
- `CODE_REVIEW` before `TEST`
- automated specialist execution for read-only analysis roles
- improvement capture into `agentMemory`
- sync into real Claude, Codex, and Gemini install directories

## What Does Not Work End To End Yet

- autonomous code authoring inside `DEV`
- bounded-write fixer execution
- fully automated branch, commit, and PR lifecycle for this repo exercised live from issue to merge
- dedicated structured runs database beyond local state/artifacts and `agentMemory`

## Pipeline

The source-of-truth pipeline policy is [pipeline/autonomous.md](pipeline/autonomous.md).

Important current behaviors:

- `CODE_REVIEW` runs before `TEST`
- code review enforces DRY, simplification, naming, style, docs/comments, and dependency concerns
- `todo.json` is a first-class local adapter
- GitHub Issues are the intended shared backlog for this repository
- lessons and patterns should be promoted into `agentMemory`

## Runtime Entry Points

Local runtime:

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root . --action full-demo
```

Agent memory validation:

```bash
PYTHONPATH=. python3 scripts/validate_agent_memory.py --project-path .
```

Host feature matrix:

```bash
PYTHONPATH=. python3 scripts/sync_prompt_pack.py print-host-features
```

## Host Sync

The repo is intended to be the single source of truth. A user pulls the repo, then syncs host installs from it.

Basic flow:

```bash
cp .env.example .env
python3 scripts/sync_prompt_pack.py check
python3 scripts/sync_prompt_pack.py sync
python3 scripts/sync_prompt_pack.py install-git-hooks
```

The sync layer now supports:

- copied pipeline and specialist prompts
- host-native instruction entrypoints
- generated config snippets for hook or MCP wiring
- periodic scheduler output for `cron`, `anacron`, `launchd`, and Windows Task Scheduler

See [examples/host-sync.md](examples/host-sync.md).

## Host Coverage

Primary hosts wired today:

- Claude
- Codex
- Gemini

Additional modeled hosts:

- Cursor
- OpenClaw

The sync tool is path-based. It does not assume one host runtime is canonical.

## Task Sources

Current supported task sources:

- `todo.json`
- GitHub Issues

Design target:

- keep adapters cohesive so other task systems or databases can map into the same canonical task model
- avoid baking source-specific logic into the orchestration phases

## Durable Learning

The system is intended to improve itself through promotion:

1. run artifacts
2. pattern candidates
3. playbooks
4. scripts or packaged skills

This learning layer should live in `agentMemory`, not only in chat history.

## Anvil Direction

The current repo runtime is Python-first and local-first. The likely execution direction is:

- keep this repository as the workflow contract, adapters, docs, and sync layer
- use `anvil` as the actual code-writing execution engine for `DEV`

That integration direction is not complete in this repository yet, but it is the intended path for full autonomous code authoring.

## Repository Backlog

Public repo:

- `https://github.com/metazen11/autonomous-agents`

This repository should use GitHub Issues as its own productization backlog. The detailed implementation roadmap is still captured in [plan.txt](plan.txt).
