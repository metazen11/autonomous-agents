# Dispatch: Keep benched Codex agents from staying active as legacy TOML profiles

**Date:** 2026-11-25 01:05 America/Los_Angeles
**Owner:** Codex orchestrator
**Checkout:** `/Users/mz/_CODING/autonomous_agents_mds`, existing branch `codex/ziggy-autonomy-workflow`

## Mechanism

The canonical Codex selection in `host_agents.json` benches `regime-filter-tuner` and `strategy-honesty-checker`, and the Markdown host sync writes only `*.md`. `check_target()` also checks only generated Markdown names. Same-name legacy `~/.codex/agents/*.toml` profiles can therefore keep stale per-task-worktree instructions active while `sync` and `check` report success.

## Ask

In this existing checkout, make host sync enforce the selected bench state for exact same-name legacy TOML profiles without deleting or overwriting them. Reuse the canonical `host_agents.json` bench list; preserve unrelated TOML profiles.

## Acceptance criteria

1. A same-name TOML for a benched canonical agent is moved from the active agents directory to the sibling `agents-bench/`, preserving bytes, during source-controlled sync.
2. A symlink, non-file, or destination collision fails with a clear error before any Markdown sync or unrelated file changes.
3. `check_target()` reports an active same-name legacy TOML as out of sync before migration.
4. Unrelated TOML files remain byte-identical and in place.
5. Regression coverage verifies migration, conflict fail-closed behavior, and unrelated-file preservation.
6. Document the exact ownership and migration behavior. Do not edit installed TOML files directly.

## Guardrails

- Do not create a worktree, switch branches, commit, or push.
- Do not alter `host_agents.json`, prompt source text, installed profile files, or `.anvil/` runtime state.
- Code ownership: `autonomous_pipeline/host_sync.py`; tests: `tests/test_host_sync.py`; documentation: `examples/host-sync.md` or the narrowest relevant source guide.
- Preserve all pre-existing dirty and untracked files in this checkout.
- Independent review must approve the exact diff before tests run.
- No production, broker, or database changes.

## Status

**Implementation verified; integration pending.** The exact same-name TOML profiles for benched canonical Codex agents are checked and moved under a per-install process/thread lock. Preflight rejects unsafe source/destination paths before other sync writes. Migration verifies source identity around no-follow linking and preserves both copies on rollback conflict. Out-of-band edits to installed profiles are outside the serialization contract.

- **Files:** `autonomous_pipeline/host_sync.py`, `tests/test_host_sync.py`, `examples/host-sync.md`
- **Independent review:** APPROVE after three review/fix cycles; final review found no remaining blockers in scope.
- **Tests:** `PYTHONPATH=. python3 -m pytest tests/test_host_sync.py -q` — 34 passed, 55 subtests passed.
- **Diff check:** `git diff --check` passed.
- **PR / landing:** Not created yet; this branch is 5 commits behind `origin/dev` and 3 commits ahead of `origin/main`. Integrate against the repository's configured legacy `dev` flow before opening the PR.
- **Preserved unrelated state:** dirty `.anvil/` runtime files, untracked `.worktrees/`, and other pre-existing working state remain untouched.
