# Changelog

## Unreleased

- Agent bench (#23): a host's `exclude` list now syncs to `<host>/agents-bench/` (no host loads it) instead of being dropped. `sync_prompt_pack.py bench list | play <stem> | sit <stem>` moves an agent between the bench and the active set and re-syncs only the changed hosts; `check` reports the bench and fails on a benched agent in the active dir. Benched on Claude and Codex: the 10 finance agents, `anvil-qa`, `anvil-qa-ui`, `regime-filter-tuner`, `strategy-honesty-checker`. Agent-description block 8855 B to 6365 B (~2214 to ~1592 tokens), 47 to 34 agents.
- Non-agent files (no `name:`/`description:` frontmatter, e.g. `agents/secret_rotator.SPEC.md`) are no longer rendered into host agent dirs.

- Context budget (#20): the rendered host instruction file shrank from 24.3 KB (~6.1k tokens) to 7.7 KB (~1.9k tokens). Iron Rules now come last and are pointed to from the top. The full rules moved to `docs/contract-reference.md` under `§XX` rule IDs, guarded by the drift and ordering tests in `tests/test_context_budget.py`.
- `scripts/measure_context.py` measures the rendered files and the agent-description blocks.
- `host_agents.json` holds the per-host agent include list. `kyc-screener` is excluded for Claude and Codex (operator, 2026-10-25); the source is kept.
- Every agent `description` is now 200 chars or less.
- Restored the billed-services rule (GitHub billed to the WFCA card). It had only been installed from the unmerged `work/billing-local-first-rule` branch.
- Documented the hook-injection budgets (`docs/contract-reference.md` §HK).
