# Architecture

This repository has moved beyond a prompt-only pack. It now has a real local runtime, but it is still intentionally split into layers so the workflow stays host-agnostic.

## Layer 1: Prompt Pack

The prompt pack defines policy, specialist roles, and handoff contracts.

Primary files:

- [pipeline/autonomous.md](../pipeline/autonomous.md)
- [agents/AGENT_AGNOSTIC_GUIDE.md](../agents/AGENT_AGNOSTIC_GUIDE.md)
- [agents/](../agents)

Responsibilities:

- pipeline phase policy
- specialist role definitions
- repo-management rules
- code review standards
- escalation conditions
- improvement and promotion policy

This layer is the source of truth for how the system should behave, regardless of host.

## Layer 2: Local Runtime

The Python runtime is the executable implementation of the core path.

Primary files:

- [scripts/run_pipeline.py](../scripts/run_pipeline.py)
- [autonomous_pipeline/runner.py](../autonomous_pipeline/runner.py)
- [autonomous_pipeline/schemas.py](../autonomous_pipeline/schemas.py)
- [autonomous_pipeline/specialists.py](../autonomous_pipeline/specialists.py)
- [autonomous_pipeline/verification.py](../autonomous_pipeline/verification.py)

Responsibilities:

- run-state persistence
- task pickup
- planning artifacts
- deterministic `DEV` command execution
- `CODE_REVIEW`
- verification and final review
- PR payload preparation
- reporting and improvement promotion

Current runtime scope is local-first. It can manage and evaluate work, but it does not yet fully author code autonomously.

## Layer 3: Task Adapters

Task sources are normalized behind a canonical task model.

Primary files:

- [autonomous_pipeline/adapters/base.py](../autonomous_pipeline/adapters/base.py)
- [autonomous_pipeline/adapters/todo_json.py](../autonomous_pipeline/adapters/todo_json.py)
- [autonomous_pipeline/adapters/github.py](../autonomous_pipeline/adapters/github.py)

Responsibilities:

- source-specific task access
- canonical normalization
- task status updates
- follow-up task creation where supported

Current adapters:

- `todo.json`
- GitHub Issues

Design rule:

- `todo.json` is one adapter, not the model
- future task systems should map into the same canonical shape

## Layer 4: Durable Memory

`agentMemory` is the durable learning backend.

Primary files:

- [autonomous_pipeline/memory/agent_memory.py](../autonomous_pipeline/memory/agent_memory.py)
- [autonomous_pipeline/memory/validation.py](../autonomous_pipeline/memory/validation.py)
- [scripts/validate_agent_memory.py](../scripts/validate_agent_memory.py)

Responsibilities:

- lesson storage
- project-scoped search
- pattern capture
- playbook promotion support

Design rule:

- artifacts are local evidence
- memory stores distilled reusable knowledge

## Layer 5: Host Integration

Host integration keeps the workflow usable in Claude, Codex, Gemini, and similar shells.

Primary files:

- [autonomous_pipeline/host_sync.py](../autonomous_pipeline/host_sync.py)
- [scripts/sync_prompt_pack.py](../scripts/sync_prompt_pack.py)
- [host-integration.md](host-integration.md)

Responsibilities:

- sync pipeline and specialist prompts
- generate host-native entrypoint files
- generate config snippets for MCP or hooks
- keep installed host surfaces aligned with the repo

Verified hosts:

- Claude
- Codex
- Gemini

Modeled hosts:

- Cursor
- OpenClaw

## Current Execution Path

The verified path today is:

1. pick a task from `todo.json` or GitHub Issues
2. plan and record run state
3. execute deterministic `DEV`
4. run `CODE_REVIEW`
5. run `TEST`
6. run final `REVIEW`
7. prepare report and PR artifacts
8. promote lessons or follow-ups

## Current Storage Model

Local state:

- `.autonomous-state.json`

Artifacts:

- `.runs/`
- configured artifact directory

Shared backlog:

- GitHub Issues

Local/offline backlog:

- `todo.json`

Durable learning:

- `agentMemory`

There is not yet a dedicated SQL or SQLite runs database for pipeline history.

## Current Constraints

Not complete yet:

- autonomous code authoring in `DEV`
- write-capable fixer specialists
- fully exercised live branch/commit/PR loop for this repo
- multi-agent write orchestration with isolated worktrees and automatic merge integration

## Near-Term Direction

The most likely architecture direction is:

- keep this repository as the policy, adapter, memory, sync, and documentation layer
- integrate `anvil` as the code-writing execution backend for `DEV`

That would let this repository stay host-agnostic while delegating actual code authoring to a stronger local coding engine.
