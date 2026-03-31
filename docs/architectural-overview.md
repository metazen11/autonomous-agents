# Architectural Overview

This file is the short-form architectural entrypoint.

For the full breakdown, see [architecture.md](architecture.md).

## Summary

This repository has four active concerns:

1. prompt-pack policy
2. local Python runtime
3. durable learning through `agentMemory`
4. host-native sync for Claude, Codex, and Gemini

## Source Of Truth

Behavioral source of truth:

- [pipeline/autonomous.md](../pipeline/autonomous.md)
- [agents/AGENT_AGNOSTIC_GUIDE.md](../agents/AGENT_AGNOSTIC_GUIDE.md)

Executable source of truth for the current local path:

- [scripts/run_pipeline.py](../scripts/run_pipeline.py)
- [autonomous_pipeline/](../autonomous_pipeline)

## Why This Split Exists

The goal is to avoid tying the workflow to one host shell.

- Claude, Codex, and Gemini can all consume the prompt-pack layer
- the Python runtime provides one deterministic local execution path
- `agentMemory` stores durable lessons and patterns
- host sync keeps installed prompt-pack surfaces current

## Current Limitation

The runtime can manage and verify work, but it does not yet fully generate and land code autonomously end to end.

## Likely Next Step

Use `anvil` as the code-writing backend for `DEV` while keeping this repo as the workflow, memory, adapter, and sync layer.
