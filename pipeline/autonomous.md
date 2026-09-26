---
name: autonomous-pipeline
description: "Thin wrapper that invokes the working composition of focused skills (/reconcile, /improve, /sprint-close, /autonomous-drain when present) under iron-rule preconditions. Replaces the prior monolithic spec — see reports/2026-05-24-autonomous-skill-audit.md for context."
---

# Autonomous Pipeline Orchestrator (thin wrapper)

This skill is a thin orchestrator that runs the project's working composition of focused skills in sequence, under explicit iron-rule preconditions. It does NOT redefine the pipeline — it sequences the skills that already implement it.

For the host-agnostic abstract spec (useful for Codex / Gemini / Anvil installs that don't have the project skills), see `pipeline/autonomous-spec-host-agnostic.md` (preserved for portability).

## What this wrapper actually does

```
PRECONDITIONS → DRAIN → IMPROVE → CLOSE
```

| Phase | Skill invoked | What it does |
|---|---|---|
| **PRECONDITIONS** | (inline checks) | PRODUCT_VISION.md read, REPO_INDEX.json consulted, runaway-detector clean, reconcile-lock available, working branch safe |
| **DRAIN** | `/autonomous-drain LABEL=<arg>` (issue #721 — promote N-lane drain pattern to a skill; until then, drive the N-lane composition inline per CLAUDE.md § Drain-the-Queue) | N-lane orchestration: tester+filer / fixer+reconciler / auditor. Pipeline ends when the labeled queue is empty for 5 consecutive polls AND auditor backlog drained. |
| **IMPROVE** | `/improve` | 8-dimension CTO scorecard + top 3 fixes. Mandatory post-sprint per CLAUDE.md. |
| **CLOSE** | `/sprint-close` | Update CHANGELOG, CLAUDE.md, ARCHITECTURE.md, AGENTS.md, HANDOFF.md, E2E_DEMO.md, etc. |

## Trigger

Invoke when the operator says any of: "run the full pipeline", "autonomous run on `<label>`", "drain `<label>` then improve and close", or types `/autonomous <label>`.

Do NOT invoke for: single-task delivery (use the composition directly), exploratory work, refactors without a queue, or anything that doesn't fit a labeled-issue queue.

## Iron Rule Preconditions (NON-NEGOTIABLE)

Before any phase runs, verify ALL of these. A failure stops the wrapper with `needs_human`.

1. **PRODUCT_VISION.md has been read this session.** CLAUDE.md line 20 calls this a hard precondition; the wrapper must not skip it.
2. **REPO_INDEX.json is fresh.** `make index --check` exit 0, OR regenerated within the last 10 commits. CLAUDE.md line 21.
3. **Runaway-subagent detector is clean.** `scripts/detect_runaway_subagents.sh 5` exits 0. If non-zero, follow `docs/runbooks/runaway-subagent.md` BEFORE proceeding.
4. **Reconcile lock available or owned by us.** `scripts/reconcile_lock.sh status` either reports `(no lock)` or a stale-PID entry the wrapper can clear via re-acquire.
5. **Working branch is safe.** Not the production trunk, not the integration trunk; clean tree (no uncommitted changes); no in-progress rebase.
6. **`make start --check` exit 0.** Dependencies + env are sane. Doesn't change state.
7. **`gh auth status` shows the expected account.** For `metazen11/psde-os` work, account must be `metazen11`, NOT `wfca-mz` (which lacks repo visibility — see memory `reference_gh_auth.md`).

If any precondition fails: write the failure to `plans/autonomous-precondition-failure-<ts>.json`, comment the cause on any related issue, exit `needs_human`.

## Iron Rule: branching contract

This wrapper MUST NOT open PRs. The branching contract in CLAUDE.md says PRs are only for `integration-trunk → production-trunk` (`develop → main`), human-reviewed. The `reconcile-gate` hook will refuse non-conforming `gh pr create` calls.

The wrapper's only path to integration is `/reconcile` (invoked inside `/autonomous-drain` Lane B per issue #721). Replace any "open a PR" language from prior versions of this skill with "run `/reconcile`."

## Iron Rule: worktree isolation

Every Lane A / Lane B / Lane C dispatched by `/autonomous-drain` runs in `.claude/worktrees/agent-<id>/`. The global `worktree-write-guard` hook (`~/.claude/hooks/worktree-write-guard.js`) actively blocks writes to paths outside the lane's worktree. This is enforcement, not advisory. See `reports/2026-05-24-runaway-subagent-postmortem.md` for the incident that drove this.

## Iron Rule: GitHub-as-queue

Queue state lives in `gh issue list --label <prefix>`. No side-channels (`/tmp/queue.json`, in-prompt task lists, etc.). Operator interrupts are lossless because the queue is in `gh`, not in a process. CLAUDE.md § Drain-the-Queue invariant 3.

## Autonomous-mode default: do not pause for confirmation

When the wrapper is invoked under `/autonomous`, productivity does NOT stop for "are you sure?" prompts. The operator is *informed* via one status line per phase transition — never asked. Stops happen only on:

- runaway detector non-zero
- reconcile lock held > 30 min by a dead PID after one stale-clear attempt
- Lane C reopens > 50% of closures in a window (Lane B fundamentally broken — abort and report)
- explicit `needs_human` from a lane

Anything else is sub-issue + push-through. The operator can interrupt at any time; pipeline resumes from `gh` state.

## Invocation

```bash
/autonomous LABEL=airbyte-e2e:           # drain the airbyte-e2e: queue, then improve, then close
/autonomous LABEL=connector-dod:         # drain the connector definition-of-done queue
/autonomous LABEL=cto-improve-2026-05    # drain a /improve finding batch
/autonomous LABEL=demo-blocker:          # drain demo-blocker triage
```

Lane budget defaults: Lane B closes ≤5 issues per dispatch, then re-dispatches. Lane C audits all closures in its window per dispatch. Override via `LANE_BUDGET=<n>`.

## Pseudocode (the actual contract)

```
fn /autonomous(label):
    # PRECONDITIONS
    for check in [product_vision_read, repo_index_fresh, runaway_clean,
                  lock_available, branch_safe, make_start_check, gh_auth_correct]:
        if not check(): exit needs_human

    # DRAIN
    if skill_exists("autonomous-drain"):
        invoke("/autonomous-drain LABEL=" + label)
    else:
        # Until issue #721 lands, drive the N-lane composition inline per
        # CLAUDE.md § Drain-the-Queue Pipeline (N-Lane Pattern).
        run_n_lane_drain_inline(label)

    # IMPROVE
    invoke("/improve")

    # CLOSE
    invoke("/sprint-close")

    # REPORT
    emit final summary to operator + handoff note
```

## Recommended specialists (registered-agent names, NOT filenames)

Use these in `Agent` tool calls via `subagent_type: <name>`. Filesystem note: the universal-pack sync renames each to `aa_<underscore>.md` on install — **do not Read the `.md` files; invoke by registered name.**

- `code-reviewer` — merge readiness
- `qa-tester` — verification selection and behavioral validation
- `security-auditor`, `dep-auditor` — security-sensitive changes
- `perf-profiler` — performance-sensitive changes
- `db-analyst` — schema, query, migration
- `infra-checker` — deployment / environment
- `soc2-auditor`, `hipaa-auditor` — compliance scope explicit
- `security-fixer`, `compliance-fixer` — bounded write scope, rollback expectations
- `skill-promoter` — mine repeated workflows
- `quality-gate` — non-trivial plans before DEV (CLAUDE.md mandate)
- `completion-auditor` — every issue close (CLAUDE.md line 30, ADR-010)
- `reconciler` — `/reconcile` sub-agent fallback when inline reconcile hits complex conflict

## What this wrapper deliberately removes

Compared to the prior version of this skill (the 343-line abstract spec, preserved at `pipeline/autonomous-spec-host-agnostic.md`):

- The detailed INIT/PICK/PLAN/DEV/CODE_REVIEW/TEST/REVIEW/PR/REPORT/IMPROVE phase definitions — those are owned by the individual skills now. Duplicating them caused drift.
- The "open a PR" language in phase 7 — conflicts with the branching contract.
- The bare specialist-name list with no execution context — replaced with explicit "registered name vs filename" guidance.
- The session-state and task_run YAML schemas — those belong in `/autonomous-drain` (#721), not here.
