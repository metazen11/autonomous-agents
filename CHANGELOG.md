# Changelog

## Unreleased

- Context budget (#20): the rendered host instruction file shrank from 24.3 KB (~6.1k tokens) to 7.7 KB (~1.9k tokens). Iron Rules now come last and are pointed to from the top. The full rules moved to `docs/contract-reference.md` under `§XX` rule IDs, guarded by the drift and ordering tests in `tests/test_context_budget.py`.
- `scripts/measure_context.py` measures the rendered files and the agent-description blocks.
- `host_agents.json` holds the per-host agent include list. `kyc-screener` is excluded for Claude and Codex (operator, 2026-10-25); the source is kept.
- Every agent `description` is now 200 chars or less.
- Restored the billed-services rule (GitHub billed to the WFCA card). It had only been installed from the unmerged `work/billing-local-first-rule` branch.
- Documented the hook-injection budgets (`docs/contract-reference.md` §HK).
