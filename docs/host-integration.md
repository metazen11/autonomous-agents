# Host Integration

This repository treats Claude, Codex, Gemini, Cursor, and OpenClaw as different host shells around the same core operating model.

## What Was Pulled In

After scanning local host installs and related repos, the stable patterns worth adopting were:

- project-level instruction entrypoints such as `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`
- host config and MCP wiring surfaces
- session and memory hooks where supported
- durable task and plan conventions such as `todo.json`, `HANDOFF.md`, and persistent memory files

The sync layer now installs or generates those surfaces per host instead of only copying one markdown prompt.

## Host Matrix

- Claude
  Uses `CLAUDE.md`, copied pipeline and agent prompts, and a generated JSON settings snippet for hook-style automation.
- Codex
  Uses `AGENTS.md`, copied pipeline and agent prompts, and a generated TOML snippet for trust and MCP wiring.
- Gemini
  Uses `GEMINI.md`, copied pipeline and agent prompts, and a generated JSON MCP snippet.

## Commands

```bash
python3 scripts/sync_prompt_pack.py print-host-features
python3 scripts/sync_prompt_pack.py check
python3 scripts/sync_prompt_pack.py sync
```

## Design Constraint

Host-native files must not fork the policy. They are entrypoints into the same prompt-pack contract:

- [pipeline/autonomous.md](../pipeline/autonomous.md)
- [agents/AGENT_AGNOSTIC_GUIDE.md](../agents/AGENT_AGNOSTIC_GUIDE.md)

If a host wants extra behavior such as hooks or MCP servers, that belongs in generated host config snippets, not in a divergent workflow definition.
