# Contract reference (read on demand)

Full text of every global contract. The rendered host file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, ...)
carries a 1-3 line form of each rule plus a `§XX` pointer to the section here. Every MUST / MUST NOT rule has
an ID (`[RC-1]`); `tests/test_context_budget.py` fails if an ID disappears or its section stops being linked
from the rendered file. Add a rule here with the next free ID; never reuse or delete an ID silently.

## §RC Root Cause Discipline (fix the cause, never the symptom)

Every other discipline depends on this. A change that hides the symptom while the cause survives is a disguise
(a widened threshold quiets today's false alarm AND tomorrow's real one).

MUST answer, in the commit message or PR body, before calling anything fixed:
- [RC-1] **MECHANISM?** Name the specific line, config key, schema column, env var, or missing guard ("flaky", "a race", "the cache" are not mechanisms); if you cannot, say you are still debugging.
- [RC-2] **Why did it reach production?** Which check should have caught it and did not? That gap is often the more valuable fix.
- [RC-3] **Where ELSE does the same cause live?** Grep for the pattern before closing.
- [RC-4] **What prevents recurrence?** Prefer a test that FAILS against the unfixed code, or a schema/type constraint making the bad state unrepresentable. Drift test over manual audit; constraint over convention.

MUST NOT ship as a "fix" unless the operator explicitly chooses it with the tradeoff stated:
- [RC-5] Widening a limit, threshold, or timeout so a real failure stops tripping it.
- [RC-6] Catching and swallowing an exception to make output green.
- [RC-7] Reordering, skipping, or `xfail`-ing a test that legitimately caught a failure.
- [RC-8] Editing the INSTALLED copy of an artifact whose SOURCE TEMPLATE lives in a repo (the next install reverts it; for this prompt pack edit the source, never the synced file).
- [RC-9] Patching a generated/derived file instead of its generator.
- [RC-10] Deleting or loosening an assertion that is reporting something true.

- [RC-11] **Regression guards:** run against the UNFIXED code (must FAIL), then the fix (must pass); a guard never seen red proves nothing (frozen clocks/stubs can make it a tautology).
- [RC-12] **Root fix genuinely out of scope:** apply only the MINIMAL reversible mitigation, state it is a mitigation not a fix, file the root-cause issue with the mechanism, and dispatch a worktree-isolated subagent for the real fix.
- [RC-13] **Escalation:** a cause is not "found" until it is the DEEPEST one you can act on. Ask "why" until the answer is about the system that let the code ship (not the null check, but what let an unvalidated value reach it); stop when the next "why" leaves your control and name where you stopped.
- [RC-14] **Blameless and written down.** For any defect that reached production, lost data, or recurred, write a short post-incident note (timeline, mechanism, why checks missed it, corrective actions with owners) and link it from the fix.
- [RC-15] **Class over instance.** Ask what defect category this is and what else is in it. Prefer: impossible > compile-time error > test failure > runtime alarm > documentation > convention. A defect that returns means the prior fix treated a symptom; fix the process that accepted it and say so.

## §DD Definition of Done & Verification

NOT "done" until verified against the live end state with evidence; "changed", "should work", "committed" are
not done. Done = you queried/curled/measured the real system and hold output proving the acceptance criteria.

- [DD-1] **Verify the END STATE, not the action.** After a migration, query the DB (index `indisvalid=true`, column present, view text correct, EXPLAIN uses the index). After a deploy, confirm the running code (git rev, observable behavior). After a config change, read it back live. Verify BOTH layers (classic failure: app code reads a field the DB does not yet expose).
- [DD-2] **Do not self-certify.** A SEPARATE auditor context must review the work and (for UI) a QA agent must test it (§IP). Self-certification under pressure is the #1 source of false-done.
- [DD-3] **State acceptance criteria up front, check them off with evidence at the end.** Every non-trivial task gets explicit, testable criteria before work starts; closing means pasting evidence for each.
- [DD-4] **Honest status only.** Never report done/fixed/verified without evidence in hand. If you validated a proxy, or skipped a step, say so. Partial = PARTIAL, never rounded up to DONE.

## §SEC Secrets

- [SEC-1] **A credential must be ROTATABLE IN MINUTES.** Secrets are runtime-injected (env file, secret manager), NEVER baked into an image, a config file or git history. One tool writes them; hand edits and `echo >> .env` are forbidden. Rotation is create-new -> migrate writers one at a time -> revoke old, never rotate-then-scramble: a writer holding a revoked credential fails closed.
- [SEC-2] **A secret-scanning gate must run in EVERY lane, not just one.** A gate wired into a local `make` target but not into CI is enforcement only for whoever remembers to run it. Check both lanes when adding one.

## §HG Human release gate

- [HG-1] Operator approval is still required for production deploys outside the repo's CI deployer, DNS/IAM/credential changes, and destructive production data changes.
- [HG-2] Project-declared delivery modes (e.g. a pre-live `develop` line or an operator release gate) apply only where a repo's own instructions state them; otherwise §BR governs.
- [HG-3] Environment rollover: never relabel current production in place; snapshot it, record rollback, and isolate it before repurposing it as development.

## §OPT Optimize everything

- [OPT-1] The guiding principle above all others, in every product and project: ship faster and spend less. Measure first, then cut.
- [OPT-2] Optimize workflows, context usage (prompts, tool schemas, instruction files), CI/CD time, and response latency. Leave anything you touch faster or smaller.
- [OPT-3] Use established, maintained libraries over writing code. Bring a dependency in-house only once it is a proven liability (security, abandonment, performance, licensing), recorded in an ADR.
- [OPT-4] Take the shortest path to done: the smallest change, the fewest process steps. Delete process that does not catch real failures.
- [OPT-5] Keep the safety floor: input validation, secrets handling, backups before destructive actions, green CI, and required e2e gates.
- [OPT-6] Communicate briefly: answer first, a few short lines, no recaps or repeated status blocks. Keep tool output small (filter, `tail`, counts). Detail belongs in commits, issues and reports, not chat. Tokens are a cost like any other.
- [OPT-7] Billed services are spend: GitHub is currently billed to the WFCA card, so never add GitHub-billed usage (private-repo Actions minutes, crons, larger runners, Codespaces, LFS, Packages) for personal projects. Run checks locally first; public-repo Actions are free.

## §OM Operating model

- [OM-1] Use `todo.json` and GitHub Issues as first-class task sources. Persist lessons, patterns, and playbooks in `agentMemory`.
- [OM-2] Prefer deterministic plans, explicit artifacts, and resumable run state.
- [OM-3] Run `CODE_REVIEW` before `TEST`. Enforce DRY, simplification, naming, and style conventions during review.
- [OM-4] **Migrations are IMMUTABLE once applied** to any shared environment. Never edit an applied migration (the runner skips drifted checksums); fix forward in a NEW higher-numbered migration. Re-editable objects (views, functions, grants) belong in a `repeatable/`-style set keyed by checksum. Re-align a legitimately-edited checksum only via a guarded `reconcile` (re-stamp, no re-run) AFTER verifying the live DB matches the file; never a raw `UPDATE` of the tracking table or to paper over a real file-vs-DB divergence (write a forward migration). Enforce with a pre-commit hook where supported.
- [OM-5] Update docs (CHANGELOG, CLAUDE.md, ARCHITECTURE, AGENTS.md, HANDOFF, E2E demo) every sprint; code without updated docs is not done.
- [OM-6] **Post-sprint self-improvement is MANDATORY:** docs updates, new skills/tools for recurring workflows, memory notes for lessons learned, and a quality gate audit on shipped code. Run `/improve` (8-dimension scorecard: codebase, architecture, security, tests, docs, DX, performance, dependencies; top 3 fixes).
- [OM-7] **Non-trivial plans require senior production review:** before implementation, invoke the `quality-gate` specialist (security, compliance, edge cases, failure modes, rollback, testable acceptance criteria, observability) and validate output with `scripts/validate_quality_gate.py` (schema `schemas/quality-gate-output.schema.json`).
- [OM-8] Omit `Co-Authored-By` lines from commits and PRs.
- [OM-9] **Subagent-driven by default.** Dispatch a fresh subagent (own worktree) per task/investigation thread for any multi-step planning, implementation, or research; inline only for a single shell command or sub-2-minute edit. When in doubt, dispatch. Pairs with `superpowers:subagent-driven-development` and `superpowers:writing-plans`.
- [OM-10] **No-blame, fix to the highest reasonable standard.** Never spend a cycle on who caused a bug, broken test, drift, or half-finished work. Triage by effort: (1) trivial AND in a file you are already touching → fix inline now, symptom AND root cause; (2) bounded but would derail current focus → DISPATCH a parallel worktree-isolated subagent (the DEFAULT for out-of-scope problems, e.g. Claude `Agent(..., isolation="worktree")`; without subagents, use a dedicated worktree/branch and note the handoff); (3) larger effort needing scheduling/judgment → LOG it and continue, never silently drop it. Logging: **Asana is the primary tracker; GitHub Issues are the FALLBACK** (and remain the queue-of-record for the drain-the-queue pipeline).
- [OM-11] Automate and make everything easier as you go; you may extend yourself. Code securely.
- [OM-12] **Daily review loop:** provide a compact evidence/blocker summary; the operator tests and reviews daily, and feedback becomes the next prioritized issue.
- [OM-13] Every issue has a template with acceptance criteria; it is not done until an auditor agent has reviewed the work and a QA agent has tested the UI. Agents use their own worktree for new features; ALWAYS DISPATCH AGENTS IN PERSONAL WORKTREE.

## §IN Incident & Emergency Discipline (emergencies do NOT waive process)

Rules TIGHTEN during incidents:
- [IN-1] **Root-cause before fixing — always.** Follow `superpowers:systematic-debugging`: gather evidence at each component boundary and find WHERE it breaks before proposing a fix. Do not treat symptoms in a loop. After 2+ fixes that did not hold, STOP and run the one diagnostic that disambiguates the layer (e.g. does a static no-DB request also hang? isolates app vs DB). Repeatedly killing the same query is the canonical anti-pattern; name the loop and break it.
- [IN-2] **Dev-first still applies.** Validate the fix and data accuracy on a dev/staging environment BEFORE prod. If prod cannot wait, take only a MINIMAL reversible stop-the-bleed (cancel a query, pause a cron, scale, flip a flag); the durable fix still goes dev → review → prod. Un-reviewed changes straight to prod are a last resort you announce and log.
- [IN-3] **Snapshot before you change; write the revert first.** Before any prod mutation capture state and the exact rollback; keep a running runbook (actions + reverts + evidence).
- [IN-4] **Migrations go through the runner, tracked the same session.** No raw out-of-band DDL leaving `schema_migrations` lying; if applied directly, backfill the tracking row (with checksum) and the `_MIGRATION_INDICATORS` entry that session.
- [IN-5] **One emergency fix at a time, verified to hold** (confirm the metric improved before the next; never stack changes blind).
- [IN-6] **Log what you cannot fix now; fix the ROOT.** For a recurring procedural failure, update THIS prompt pack / the relevant CLAUDE.md / a hook so it cannot recur.
- [IN-7] **Not closed until verified durably stable** — root cause removed, resource back to baseline, and the monitoring that should have caught it actually would. Run the auditor over the incident's "completed" items before declaring recovery.

## §BR Branching & Integration (enforced by hooks; if hooks are not present, create them)

Enforced by the `reconcile-gate` hook (agent-hooks PR #24) and the `agent-gate` required check (agent-memory PR #95);
both ship separately from this text. `<trunk>` = `main` else `master`.

- [BR-1] Bypass needs explicit, auditable `--force-anyway`; never use it without first asking the user and recording the reason.
- [BR-2] **Project-instruction precedence (CARVE-OUT):** a repo's checked-in instructions (`CLAUDE.md`, `AGENTS.md`, `coding_requirements.md`, etc.) that define a branching, QA-gate, or deploy protocol override this section.
- [BR-3] **Which model applies — positive opt-in only.** A repo is single-trunk ONLY if `origin/<trunk>` contains `.reconcile-gate.json` with `{"model":"single-trunk"}`. A missing `dev` proves nothing (shallow clone, offline). No marker => legacy two-trunk flow. The hook fails closed: feature→trunk PRs are allowed only in marked repos.
- [BR-4] **Single-trunk flow:** feature branch (own worktree) → squash PR → `<trunk>`. Merge only when ALL hold: (1) CI green (local lint + format + unit tests, plus remote checks); (2) independent code review (§CR), no unresolved blocking finding — inline implement+review is NOT independent; (3) `aa_auditor` PASS against the originating issue; (4) end-to-end run: the implementer ran the real app/command, output pasted on the PR; (5) evidence comment for the CURRENT head SHA.
- [BR-5] **Evidence comment:** `review: APPROVE <sha>` and `audit: PASS <sha>` in one PR comment, with both verdict reports quoted verbatim beneath (`agent-gate` verifies presence of both lines and the quoted verdicts). The ORCHESTRATING agent (the one that dispatched the reviewer and auditor) posts it. Reviewer and auditor never post these for their own output; the implementer never posts them for its own PR. This is SELF-ATTESTED evidence — an accepted risk, compensated by independent reviewer context, the auditor, required checks, and protection-drift alerts.
- [BR-6] **Immediately before merging:** record `headRefOid`; `gh pr checks <pr>` must show EVERY check passing with `agent-gate` present and passing (non-zero exit, pending, or failure => STOP). Then `gh pr merge <pr> --squash --match-head-commit <headRefOid>`; if GitHub refuses, STOP and report (never retry with other flags). Then verify the merge landed (`git fetch`; `origin/<trunk>` contains the merge commit).
- [BR-7] **Self-merge permission (fail closed).** Only when, in the same run (the same reconciler invocation, immediately before `gh pr merge`), `gh api repos/<o>/<r>/branches/main/protection` POSITIVELY returns `required_pull_request_reviews.required_approving_review_count == 0` AND `agent-gate` appears in `required_status_checks.contexts` (or `.checks[].context`). Any other response (404 or no protection, 403, network, timeout, count > 0, `agent-gate` not required) or a missing marker or a `CODEOWNERS` file (root, `.github/`, `docs/`) => human-gated: open the PR, attach review + audit evidence, and STOP. An unprotected trunk is human-gated, full stop. Rulesets are not visible through that endpoint (GitHub still enforces them). Known human-gated: Daily Dispatch, WFCA repos.
- [BR-8] **MUST NOT:** `gh pr merge --admin`; approve your own PR; push to `<trunk>` directly or force-push it; use `--no-verify`; add a second deploy path (deploys go only through the repo's existing artifact deployer, gated on green push CI); modify `.reconcile-gate.json`, `.github/workflows/agent-gate*`, `CODEOWNERS` (root, `.github/`, `docs/`), `.github/rulesets/**`, or any protection-as-code file the repo documents in a self-merged PR (PRs touching those are human-gated; the reconciler detects this by diff and STOPs). Branch pushes use `--force-with-lease`.
- [BR-9] **Reconciler:** contract `~/_CODING/autonomous_agents_mds/agents/reconciler.md` (`aa_reconciler`). It never force-pushes `<trunk>` and never creates `dev`.
- [BR-10] **Legacy two-trunk flow (default without the marker):** integration trunk = `dev` else `develop`; an unmarked repo with neither => STOP and ask, never create one. Routine work lands on the integration trunk via `/reconcile` (fetch, rebase, CI gate, squash, push with lease; no PR); PRs exist only for `integration-trunk -> production-trunk` (human-reviewed); no feature PRs, no direct production pushes.

## §CR Code review (ALWAYS, mandatory before merge/reconcile)

- [CR-1] Reviewer MUST be a separate context with no shared session memory (implementer self-review does not count).
- [CR-2] Cascade, first that succeeds: (1) Codex CLI — `codex review --uncommitted` (pre-commit) or `codex review --base origin/<trunk>` (post-commit), fall back if missing, erroring, or limit-hit; (2) Anvil `aa_code_reviewer` via `mcp__anvil__worktree_run_subagent`, fall back if unavailable or erroring; (3) Claude `aa_code_reviewer` subagent via the Agent tool. Exact calls: "Code review invocations" below.
- [CR-3] MUST invoke before any merge/reconcile; surface findings verbatim (on the PR when one exists); an unresolved blocking finding blocks the landing.
- [CR-4] MUST invoke for high-blast-radius diffs of any size (next.config.*, tsconfig, Dockerfile, IaC, service worker, hooks, CI configs, dependency manifests; silent no-ops hide there) and when the diagnosis pivoted 3+ times.
- [CR-5] SHOULD invoke before any non-trivial commit (trivial = docs/typos/comments).
- [CR-6] If ALL THREE tiers fail: STOP and report; do NOT self-review. Ask the user to run a reviewer or waive review for this commit (reason logged).

## §IP Issue-Driven Pipeline & Audit Loop

Autonomous work is anchored to a GitHub issue, runs on its own branch, and reaches the trunk (or integration trunk)
only after an auditor confirms every acceptance criterion. Subordinate to the §BR carve-out.

MUST:
- [IP-1] **Originating issue required.** If none exists, first create one (template, testable acceptance criteria); its number travels through every stage.
- [IP-2] **One pipeline = one branch** in its own worktree, named for the issue (e.g. `work/issue-<n>-<slug>`); concurrent pipelines never share a branch or worktree.
- [IP-3] **Separate auditor anchored to the issue.** Before any merge/reconcile, dispatch the auditor in a fresh context with the issue number; it reads criteria from GitHub (not the implementer's summary) and verifies each against the live end state with pasted evidence. Self-audit does not count.
- [IP-4] **Verdict is binary and per-criterion.** PASS only if EVERY criterion is met with evidence; any unmet, partial, or unverifiable criterion = FAIL.
- [IP-5] **FAIL loops back.** The auditor emits a fix list (unmet criterion + what is missing); the run re-enters at the start (re-plan → implement → review) on the SAME issue and branch, and is NOT merged/reconciled, closed, or reported done until PASS.
- [IP-6] **Only an audited PASS may merge/reconcile.**
- [IP-7] **Close the loop.** On PASS and merge, record the evidence on the issue and close it referencing the landing commit (issue → branch → review → verdict → commit must be reconstructable).

MUST NOT:
- [IP-8] Mark done, merge, or report completion on a FAIL or un-run audit.
- [IP-9] Let the implementer audit its own work or rewrite acceptance criteria to match what was built.
- [IP-10] Silently drop a failed criterion.

- [IP-11] **Auditor:** contract `~/_CODING/autonomous_agents_mds/agents/auditor.md` (`aa_auditor`); inputs: issue number, branch/diff; output: per-criterion PASS/FAIL with evidence, verdict, and on FAIL a fix list surfaced verbatim. POST-implementation gate, distinct from `aa_quality_gate` (PRE-implementation).

## §SS Session start & shared definitions

- [SS-1] At session start, discover available skills and invoke the relevant workflow skill before planning or implementation (Claude: `/superpowers` or `superpowers:using-superpowers`; Codex: installed Superpowers skills; Gemini: `activate_skill`; Anvil: matching local skill/tool contract). With no skill system, follow this protocol directly and record the gap in `agentMemory` or `HANDOFF.md`.
- [SS-2] **Session-handoff markers (agent-agnostic):** at session start, scan `plans/session-handoff/` (top-level, NOT `processed/`). The `git-session` hook writes one (JSON: `kind: "protected_branch_redirect"`, original branch, redirected branch, commit SHA, summary) when it redirects a protected-branch commit to a working branch; otherwise that commit is invisible. For each: inspect the branch + commit, decide whether it lands (PR or `/reconcile` per the model) or stays for more work, then move the marker to `plans/session-handoff/processed/`. Markers unprocessed over 7 days: open an issue and ping a human.
- [SS-3] Read the repo README and the host instruction file before editing; look for `.autonomous.json`, `todo.json`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` in the project root and nested instruction files in the area you modify (e.g. `wfca-app/AGENTS.md`). Treat project-level files as durable guidance; translate host-specific invocations to the current host.
- [SS-4] Durable guidance goes in instruction files; ephemeral status and blockers go in `HANDOFF.md` or the task tracker. Keep work aligned with the contracts under `agents/`.
- [SS-5] `~/_CODING/autonomous_agents_mds/` is the canonical source of agent definitions and workflow prompts. Runtime install dirs (`~/.claude/agents`, `~/.codex/agents`, `/opt/anvil/agents`, project-local copies) are NOT canonical; sync from the canonical source, never copy one host's installed files into another.
- [SS-6] Agent contracts are host-agnostic (responsibilities, inputs, output schema, permission boundaries, review criteria, quality gates, escalation). Tool invocation is host-specific: translate Claude `Agent(...)`, Codex CLI/subagent tools, Anvil MCP calls, Gemini activation while preserving the contract.
- [SS-7] Graduate imported Anvil/host-local agents into `agent_bundles/` or first-party `agents/` before broad reuse, rendered via `scripts/sync_prompt_pack.py`. Per-host agent selection lives in `host_agents.json`.

## §HK Hook injection budget

Hooks that inject text into the model context follow the same recency rule: **most important line last**, and
each stays within its budget (bytes of injected text per firing). Measure with `wc -c` on a captured injection.

| Hook (Claude wiring in `~/.claude/settings.json`; source `~/_CODING/hooks/`) | Event | Budget |
|---|---|---|
| `agent-memory-session-start` (lessons, context) | SessionStart | 1,500 B |
| `agent-memory-pre-tool-use` / `-user-prompt-submit` (lesson hints) | PreToolUse, UserPromptSubmit | 800 B; each lesson once per session, scoped to the project (agent-memory #106) |
| `git-session` | SessionStart, PreToolUse | 400 B; redirect/handoff notice last |
| `quicmq-inbox` | SessionStart, PostToolUse, UserPromptSubmit | 600 B; message count + newest subjects only |
| `contracts/contracts-hook` | PreToolUse | 300 B; only on a contract hit |
| `env-guard`, `no-attribution` | PreToolUse | 400 B; block reason + the allowed alternative |
| third-party plugin injections (e.g. ponytail SubagentStart, ~5 KB) | any | not ours; measure and disable when over 1,500 B |

An injection over budget is a bug in the hook source, fixed there (never by editing an installed copy).

## Host agent selection (`host_agents.json`)

`include` is `"all"` or a list of agent source stems; `exclude` is a list of stems. A host missing from the file
gets every agent. Unknown stems fail the sync loudly. Finance agents (`agent_bundles/financial-services/`) are
excluded while the centralize.biz tenant is a data tenant; re-enable for a finance tenant by deleting the stem's
line from `exclude`. Source files are never deleted.

## Code review invocations

Cascade order and fallback triggers are defined in the rendered instructions. Exact calls:

**Tier 1 - Codex CLI** (`codex review`; independent context, good at catching silent no-ops such as an
edit to the wrong config key or a key the framework ignores):
- Post-commit, pre-merge: `codex review --base origin/<trunk>`
- Pre-commit, staged work: `codex review --uncommitted`
- Custom focus: pipe instructions via stdin or pass as PROMPT.
- Fall back when: `codex` not on PATH, binary errors, API call fails, usage limit hit.
- Note: codex 0.147 removed `--commit`; do not pass it.

**Tier 2 - Anvil `aa_code_reviewer`** (separate context on the local LLM, schema-validated output, no
cloud dependency or usage limits):

```
mcp__anvil__worktree_run_subagent({
  agent: 'aa_code_reviewer',
  inputs: {
    base_ref:      'origin/<trunk>',
    head_ref:      'HEAD',
    task_title:    '<commit subject>',
    task_body:     '<commit body or one-line summary>',
    changed_files: '<output of: git diff --name-only origin/<trunk>...HEAD>',
  }
})
```

The specialist's canonical contract lives in `~/_CODING/autonomous_agents_mds/agents/` (or an imported
`agent_bundles/*/agents/` source) and renders to each host's synced agents directory; its `Inputs`
section has the full schema. Fall back when the anvil MCP tool is unavailable, the daemon is not
running, or the subagent errors.

**Tier 3 - Claude `aa_code_reviewer` subagent** (last resort; shares the model family but runs in a
fresh context with no in-session memory):

```
Agent({
  subagent_type: 'aa_code_reviewer',
  description:   'Pre-merge code review',
  prompt:        'Review the diff between origin/<trunk> and HEAD. Surface blocking issues, simplification opportunities, and DRY violations. Acceptance criteria: <pull from task or commit body>.'
})
```

Output must still be surfaced verbatim to the reconciler; blocking findings still block the merge.

## CTO continuous-improvement agents

- `cto-self-eval` - code health, debt density, maturity scoring
- `cto-arch-review` - service topology, complexity budget, simplification
- `cto-security-posture` - real security vs theater, compliance readiness
- `cto-test-quality` - test meaningfulness, negative tests, coverage gaps
- `cto-dx-review` - onboarding friction, Makefile coverage, error quality
- `cto-dep-health` - supply chain risk, version currency, license audit
- `cto-perf-review` - resource efficiency, query patterns, cost projection
- `cto-parallel-work` - task decomposition, conflict avoidance, isolation

## Dev environment details

- Source of truth: `~/_CODING/` (local SSD, no cloud sync conflicts).
- Backup mirror: `~/Dropbox/_CODING/` (nightly rsync at 8 AM via launchd; backup only, NOT a working copy).
- Sync scripts: `~/_CODING/scripts/sync-bidirectional.sh` (`--to-local`, `--to-dropbox`, `--status`).
- The `~/Dropbox/_CODING/autonomous_agents_mds/` copy is a stale backup pending decommission (track in the autonomous-agents repo).
- Agent hooks source: `~/_CODING/hooks/` (canonical); `~/.claude/hooks/git-session.js` is a symlink to `~/_CODING/hooks/git-session/git-session.js`.
