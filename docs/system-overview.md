# System Overview

This repository is designed as a host-agnostic autonomous delivery system with one source of truth.

## Model

There are four layers:

1. Prompt pack
2. Local runtime
3. Durable memory
4. Host integration

## Prompt Pack

The prompt pack is the policy and role layer.

- [pipeline/autonomous.md](../pipeline/autonomous.md)
- [agents/AGENT_AGNOSTIC_GUIDE.md](../agents/AGENT_AGNOSTIC_GUIDE.md)
- [agents](../agents)

This layer is intended to be usable from Claude, Codex, Gemini, or another host with equivalent capabilities.

What it defines:

- pipeline phases
- specialist responsibilities
- input and output contracts
- escalation rules
- improvement policy

## Local Runtime

The Python runtime is the execution engine.

- [autonomous_pipeline](../autonomous_pipeline)
- [scripts/run_pipeline.py](../scripts/run_pipeline.py)

This layer is local-first and host-independent. It handles:

- task pickup
- local run state
- artifacts
- verification execution
- specialist execution
- PR preparation
- promotion of improvements

Current task sources:

- `todo.json`
- GitHub Issues

## Durable Memory

`agentMemory` is the durable learning layer.

- [docs/agent-memory.md](agent-memory.md)
- [scripts/validate_agent_memory.py](../scripts/validate_agent_memory.py)

Memory stores distilled knowledge:

- lessons
- patterns
- promotion candidates
- future playbook material

Memory is not the artifact store. Raw logs stay local in artifacts.

## Storage

Today the system is local-first.

Run state:

- `.autonomous-state.json`

Artifacts:

- `artifacts/`
- `.runs/`

Task state:

- `todo.json` for local/offline work
- GitHub Issues for shared/public backlog

Durable learning:

- `agentMemory`

There is not yet a dedicated SQL or SQLite run-history database for pipeline executions.

## Host Integration

The design is host-agnostic, but the verified execution path today is the local Python runtime.

Current practical model:

- Claude can use the synced prompt pack and the local Python runtime
- Codex can use the same prompt pack concepts and the local Python runtime
- Gemini can use the same prompt pack concepts and the local Python runtime

What is shared across hosts is the prompt-pack contract and the local runtime. What is not yet verified is a host-native runtime entrypoint for each host beyond file sync and manual/local CLI invocation.

The sync layer models host-native surfaces explicitly:

- Claude: `CLAUDE.md`, copied prompt pack, generated hook/settings snippet
- Codex: `AGENTS.md`, copied prompt pack, generated TOML/MCP snippet
- Gemini: `GEMINI.md`, copied prompt pack, generated MCP snippet

The intent is to absorb the best stable patterns from each host:

- project-level instruction entrypoints
- host config and MCP wiring
- memory/session hooks where supported
- persistent task and plan conventions

See [host-integration.md](host-integration.md).

## Host Sync

Installed host copies are updated from this repo using:

- [scripts/sync_prompt_pack.py](../scripts/sync_prompt_pack.py)
- [autonomous_pipeline/host_sync.py](../autonomous_pipeline/host_sync.py)

Recommended model:

1. this repo is the source of truth
2. user pulls latest changes
3. sync tool updates Claude, Codex, Gemini, Cursor, OpenClaw, or other configured hosts

## Current State

Implemented:

- host-agnostic prompt pack
- Python runtime
- `todo.json` adapter
- GitHub Issues adapter
- local run state and artifacts
- verification execution
- automated specialist execution for several read-only roles
- improvement promotion flow
- host sync tooling
- `agentMemory` validation and lesson integration
- generated host instruction entrypoints and config snippets for the primary hosts

Not fully implemented:

- autonomous code-authoring in `DEV`
- bounded-write fixer execution
- dedicated runs database
- full end-to-end PR automation exercised live against GitHub in this repo
- full `anvil` integration as the `DEV` execution backend

## Recommended Usage

For shared project tracking:

- use GitHub Issues

For local/offline execution:

- use `todo.json`

For durable learning:

- use `agentMemory`

For host installs:

- use the sync tool and keep this repo as source of truth
