# Agent-Agnostic Prompt Pack Contract

This repository is a prompt pack, not a runtime. The host orchestrator is responsible for:

- injecting task context, repo context, and changed files
- enforcing tool permissions and write scopes
- providing persistent memory when available
- capturing artifacts, logs, and structured outputs
- handling retries, escalation, and task tracking

Every specialist prompt in this pack should be invoked against the same neutral contract.

## Cross-Host Project Files

Different hosts expose different top-level instruction files, but the operating model should stay consistent.

- Claude commonly reads `CLAUDE.md`
- Codex commonly reads `AGENTS.md`
- Gemini commonly reads `GEMINI.md`

When these files exist, they should agree on:

- task sources such as `todo.json` and GitHub Issues
- memory and playbook expectations
- code review standards
- branch, commit, and PR authority

Optional supporting files:

- `HANDOFF.md` for ephemeral session state and next-step context
- `memory/*.md` for durable project-specific notes when a host supports local memory files

Do not treat host-specific filenames as separate policies. They are different entrypoints into the same contract.

## Operational Responsibility Contract

The host orchestrator must assign both role responsibility and repo authority before execution.

### Required Responsibility Fields

```yaml
agent_contract:
  role: orchestrator | planner | developer | code_reviewer | tester | reviewer | fixer | promoter
  mode: read_only | bounded_write | integration_owner
  branch_authority: none | isolated_branch | orchestrator_branch
  commit_authority: false | true
  pr_authority: false | true
  allowed_write_scope: [string]
  handoff_required: true
```

### Role Expectations

- `orchestrator`
  Owns branch strategy, final integration, commit sequencing, PR creation, and state transitions.
- `planner`
  Read-only. Produces decomposition, risk notes, and verification plan.
- `developer`
  Bounded write. Owns explicit files or modules only.
- `code_reviewer`
  Read-only. Reviews changed files and affected dependencies before broader testing. Must identify simplification opportunities, DRY issues, naming or style convention drift, and documentation or commenting gaps.
- `tester`
  Read-only plus command execution unless explicitly allowed to add tests.
- `reviewer`
  Read-only. Focuses on final merge readiness after verification.
- `fixer`
  Bounded write. May only remediate explicit findings inside explicit write scope.
- `promoter`
  Read-only relative to repo code. May create memory entries and follow-up tasks.
- `quality_gate`
  Read-only. Reviews plans and issues for production readiness. Produces structured JSON output validated against `schemas/quality-gate-output.schema.json`. Blocks vague, unsafe, or incomplete work from reaching implementation.

### Repo Management Rules

- Only the orchestrator should create the final integration commit by default.
- Only the orchestrator should open or update the final PR by default.
- Worker agents must not edit files outside `allowed_write_scope`.
- Overlapping write scopes must be serialized or escalated.
- Every handoff must report `changed_files`, `artifacts`, `verification_run`, and `handoff_status`.
- If branch state is unsafe or unrelated local changes make ownership ambiguous, return `needs_human`.

## Standard Invocation Contract

Provide these inputs when available:

```yaml
run_context:
  project_name: string
  repo_root: string
  branch: string
  base_ref: string
  head_ref: string
  task_id: string
  task_title: string
  task_body: string
  acceptance_criteria: [string]
  risk_flags: [string]
  changed_files: [string]
  allowed_write_scope: [string]
  artifacts_dir: string
  issue_url: string
  pr_url: string
```

## Memory Integration

If the host provides a memory layer:

- load only project-relevant memory before execution
- prefer concise pattern memory over raw historical logs
- write back only durable learnings, not transient run noise
- keep memory scoped by project and agent role

If no memory layer is available:

- continue without error
- report `memory_status: unavailable`

## Continuous Improvement Loop

Do not treat all memory as equal. Promote knowledge through stages:

1. `run artifact`
   Raw evidence such as commands, logs, timings, and outputs.
2. `pattern candidate`
   A repeated sequence that succeeded more than once or clearly prevented failure.
3. `playbook`
   A validated workflow with prerequisites, commands, expected outputs, and rollback notes.
4. `skill`
   A reusable prompt, script, or adapter worth packaging into the repository.

Promotion rules:

- never promote from a single noisy run
- require evidence that the pattern is reusable
- prefer scripts for deterministic command sequences
- prefer prompts for judgment-heavy workflows
- deprecate stale playbooks when the environment changes

## Automation Harvesting

After a successful task, the orchestrator should ask:

- which commands were repeated manually
- which decision branch recurred across runs
- which prerequisite checks were rediscovered
- which verification steps were necessary every time

If a sequence is stable and high-frequency:

- capture it as a script, make target, or task adapter
- store a concise summary in memory
- create a follow-up issue if packaging is deferred

## Output Contract

Each agent should produce:

```yaml
status: success | needs_human | failed
summary: string
findings: []
evidence: []
artifacts: []
follow_up: []
memory_status: loaded | skipped | unavailable
```

Specialists may extend this schema, but they should not replace it.

For agents involved in repo management, also include when available:

```yaml
changed_files: [string]
verification_run: [string]
handoff_status: ready_for_merge | ready_for_test | blocked | needs_human
```

## Severity Vocabulary

- `blocker`: unsafe to merge or proceed
- `high`: should be fixed before release
- `medium`: valid issue, can be scheduled
- `low`: useful improvement, not urgent

## Write Scope Rules

- Read-only agents must not modify repo files.
- Fixer agents may only edit files explicitly allowed by the orchestrator.
- If required files fall outside write scope, return `needs_human`.

## Escalation Rules

Return `needs_human` instead of guessing when:

- required credentials or external systems are unavailable
- the repo is in a conflicting or unsafe git state
- the requested change requires destructive or production-impacting actions
- the task intent conflicts with stated safety constraints

## GitHub Issues Tracking

If the host uses GitHub Issues:

- task pickup should record the selected issue number and URL
- each phase should append structured progress notes or artifacts
- blocker findings should map to either a checklist item or a follow-up issue
- a parent issue may own subtasks represented as issue checklists or linked child issues

## Artifact Expectations

Prefer durable artifacts over prose-only claims:

- command transcripts
- test output
- diff stats
- review findings
- security scan summaries
- generated plans

For self-improvement, also capture:

- successful command sequences
- failed command sequences and why they failed
- environment prerequisites
- benchmark deltas before and after workflow changes

Store paths in the output schema when the host provides an artifacts directory.
