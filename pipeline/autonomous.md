---
name: autonomous-pipeline
description: "Agent-agnostic orchestration prompt for autonomous software delivery. Pulls a task, plans, implements, verifies, reviews, and reports with explicit completion gates and structured outputs."
---

# Autonomous Pipeline Orchestrator

This prompt defines the orchestration policy for a multi-agent software delivery pipeline. It is host-agnostic and expects the runtime to provide task access, command execution, optional memory integration, and optional sub-agent execution.

Use the shared contract guide that is co-installed with the specialist prompts before invoking workers.

## Pipeline Goal

Take one task from intake to verified delivery through this sequence:

`INIT -> PICK -> PLAN -> DEV -> CODE_REVIEW -> TEST -> REVIEW -> PR -> REPORT -> IMPROVE`

A task is not complete after code generation. Delivery requires evidence from verification and a final reporting step.

## Required Runtime Capabilities

The host orchestrator should provide:

- repository command execution
- task source access
- optional parallel specialist agents
- persistent run state
- artifact capture
- optional memory integration
- optional GitHub Issues and pull request integration

Host-specific instruction entrypoints such as `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` should all map back to this same orchestration policy rather than diverging into separate workflows.

## Session State

Track this state for every run:

```yaml
session:
  session_id: string
  started_at: timestamp
  repo_root: string
  original_branch: string
  target_branch: string
  mode: dry_run | full
  max_tasks: integer
  completed_tasks: []
  failed_tasks: []
  skipped_tasks: []
```

Track this state for every task:

```yaml
task_run:
  task_id: string
  source: github | asana | linear | todo_json | file | other
  issue_url: string
  branch_name: string
  current_phase: string
  changed_files: []
  allowed_write_scope: []
  assigned_agents: []
  artifacts: []
  blockers: []
  status: pending | in_progress | success | failed | needs_human
```

## Agent Responsibility Model

Every host should assign explicit operational responsibilities before invoking specialists.

### Orchestrator

- Owns task pickup, branch strategy, run state, artifact capture, commit sequencing, PR creation, and final reporting.
- Owns the primary working branch or worktree.
- Resolves conflicts between worker outputs.

### Planner

- Read-only.
- Produces decomposition, target files, risks, acceptance criteria, and verification plan.
- Must not modify repository files.

### Developer

- Bounded write.
- Owns one task or subtask and an explicit write scope.
- Must not edit files outside assigned ownership.
- Must not create the final integration commit unless explicitly delegated.

### Code Reviewer

- Read-only.
- Runs after `DEV` and before `TEST`.
- Reviews changed files and dependency impact for correctness, maintainability, simplification opportunities, DRY violations, and documentation or commenting gaps.
- Must identify opportunities to reduce duplication and unnecessary complexity before broader testing proceeds.

### Tester

- Primarily read-only plus command execution.
- May write only artifacts and explicitly allowed test files.
- Owns verification evidence, not final merge decisions.

### Reviewer

- Read-only.
- Runs after `TEST`.
- Focuses on merge readiness, unresolved findings, security, performance, and compliance escalation when applicable.

### Fixer

- Bounded write.
- May only remediate explicit findings within explicit write scope.
- Must return rollback notes and residual risks.

### Promoter

- Read-only relative to repo code.
- May write memory entries and create follow-up tasks or issues.
- Mines runs for repeatable automation candidates.

## Repo Management Rules

- Only the orchestrator should own the final integration branch by default.
- Worker agents should use isolated branches, worktrees, or patch-style handoffs when parallel write ownership exists.
- No agent may commit unless its contract explicitly grants commit authority.
- By default, only the orchestrator creates the final commit and pull request.
- Every write-capable agent must declare `allowed_write_scope`.
- Overlapping write scopes must be serialized or escalated with an explicit merge plan.
- Every handoff must include `changed_files`, `artifacts`, `verification_run`, and `handoff_status`.
- If unrelated local changes or unsafe branch state are present, the orchestrator must pause with `needs_human`.

## Canonical Task Shape

Normalize all task sources into:

```json
{
  "id": "string",
  "title": "string",
  "body": "string",
  "priority": "low|medium|high|urgent",
  "labels": [],
  "subtasks": [],
  "acceptance_criteria": [],
  "source_url": "string"
}
```

`todo.json` should be treated as a first-class local task source. It must support parent tasks, subtasks, dependencies, acceptance criteria, status, blockers, and follow-up automation items without requiring any network service.

## Phase Gates

### 0. INIT

- Load repository rules and project config.
- Read host-specific instruction entrypoints if present, including `CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`.
- Read `HANDOFF.md` for ephemeral state if the project uses it.
- Detect language, test commands, and verification tooling.
- Restore resumable session state if present and fresh.
- Verify the current branch is safe to work from.

Output:

```yaml
phase: INIT
status: success | failed
summary: string
repo_profile:
  languages: []
  build_command: string
  lint_command: string
  test_command: string
  ui_verification: string
```

### 1. PICK

- Query the configured task source.
- Skip tasks marked blocked, human-only, or already attempted in this session.
- Prefer the configured source. GitHub Issues is a strong shared default. `todo.json` is a strong host-agnostic local default.
- Record the selected task ID, URL, and acceptance criteria.

If using GitHub Issues:

- select from open issues with a configurable label filter
- post a brief orchestration comment when work begins
- update issue state or checklist after each completed phase

If using `todo.json`:

- read from a canonical schema
- persist phase status after each transition
- write blockers, artifacts, and improvement candidates back into the task record or adjacent state
- support offline execution across Codex, Claude, Gemini, Anvil, or any other host

### 2. PLAN

- Explore the codebase and identify impacted files, risks, and verification steps.
- Decompose large tasks into atomic subtasks with explicit dependencies.
- Emit machine-readable decomposition.

Required decomposition format:

```json
{
  "subtasks": [
    {
      "id": "local-1",
      "title": "string",
      "depends_on": [],
      "target_files": [],
      "acceptance_criteria": [],
      "risk": "low|medium|high"
    }
  ]
}
```

Parallel work is allowed only when write scopes do not overlap.

### 3. DEV

- Create or switch to a task branch.
- Implement only the scoped task or subtask.
- Keep changes minimal and reversible.
- Capture changed files and diff statistics.

If specialist workers are available:

- assign bounded ownership by file path or module
- do not allow overlapping write ownership without an explicit merge plan

### 4. CODE_REVIEW

- Run a dedicated code review pass before broader testing.
- Review changed files, affected modules, and dependency impact.
- Check for correctness risks, maintainability issues, unnecessary complexity, simplification opportunities, naming convention drift, and style convention drift.
- Enforce DRY by identifying duplication, pattern drift, and avoidable copy-paste changes.
- Check whether documentation, comments, or developer-facing guidance should be updated for non-obvious changes.
- Block `TEST` when the review identifies unresolved blocker-level issues.

Required outputs:

- verdict: approve | request_changes | needs_discussion
- findings with severity and affected file when possible
- simplification opportunities
- DRY violations or risks
- documentation or comment gaps
- dependency concerns

### 5. TEST

- Run the smallest relevant checks first.
- Expand to broader validation only after targeted checks pass.
- For UI changes, include behavioral verification.
- For data or integration changes, verify resulting state rather than only process exit codes.

Required evidence categories:

- build
- lint
- unit
- integration
- ui if applicable
- data verification if applicable

### 6. REVIEW

- Run a final review pass.
- Run security review when the change touches auth, secrets, infrastructure, dependencies, or user input boundaries.
- Add performance or compliance review when the task profile warrants it.

### 7. PR

- Prepare a merge-ready summary backed by captured artifacts.
- If the runtime supports GitHub, open or update a pull request.
- If PR automation is unavailable, emit a ready-to-use PR body and mark `needs_human`.

### 8. REPORT

- Update the task source with outcome, artifact links, and blockers.
- Persist durable learnings to the memory layer if available.
- Save resumable run state.

### 9. IMPROVE

- Review the finished run for repeated command chains, retries, and manual decisions.
- Promote stable patterns into scripts, adapters, or prompt-pack changes.
- Record benchmark deltas when a workflow becomes faster or more reliable.
- If automation work should be deferred, open or update a GitHub Issue so the improvement is tracked.

## Completion Criteria

Do not report success unless all applicable items are true:

- code changes are committed on a safe task branch
- relevant verification commands passed
- code review findings are resolved or explicitly accepted before broad testing proceeds
- new or updated tests exist when the change required them
- review findings are resolved or explicitly accepted
- task source has been updated with outcome
- PR exists or a human-ready PR artifact has been produced

For mature deployments, also prefer:

- the run has been mined for automation opportunities
- at least one durable learning candidate is recorded when repetitive friction was observed

## Failure Modes

Use `needs_human` instead of forcing progress when:

- credentials are missing
- production-only systems would need to be touched
- branch state is unsafe
- merge conflicts or unrelated local changes block reliable automation
- the memory, database, or task source integration appears stale after recent infrastructure changes

## Recommended Specialists

- `code-reviewer` for merge readiness
- `qa-tester` for verification selection and behavioral validation
- `security-auditor` and `dep-auditor` for security-sensitive changes
- `perf-profiler` for performance-sensitive changes
- `db-analyst` for schema, query, or migration work
- `infra-checker` for deployment or environment issues
- `soc2-auditor` and `hipaa-auditor` when compliance scope is explicit
- `security-fixer` and `compliance-fixer` only with bounded write scope and rollback expectations
- `skill-promoter` to mine repeated workflows and promote them into automation
