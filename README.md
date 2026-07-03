# Autonomous Agents

Host-agnostic prompt pack and local Python runtime for autonomous software delivery.

This repository currently provides:

- a shared orchestration policy for `INIT -> PICK -> PLAN -> DEV -> CODE_REVIEW -> TEST -> REVIEW -> PR -> REPORT -> IMPROVE`
- specialist agent contracts under [agents/](agents)
- a runnable local Python runtime under [autonomous_pipeline/](autonomous_pipeline)
- task adapters for `todo.json` and GitHub Issues
- durable learning through `agentMemory`
- host sync tooling for Claude, Codex, Gemini, and Anvil

This repository is not yet a fully self-driving production orchestrator. The verified path today is a local-first runtime with real task pickup, artifacts, review/test flow, and host-native prompt-pack sync.

## Start Here

- [docs/system-overview.md](docs/system-overview.md)
- [docs/architectural-overview.md](docs/architectural-overview.md)
- [docs/host-integration.md](docs/host-integration.md)
- [examples/README.md](examples/README.md)

## Current Architecture

There are four layers:

1. Prompt pack
2. Local runtime
3. Durable memory
4. Host integration

Prompt pack:

- [pipeline/autonomous.md](pipeline/autonomous.md) — orchestration policy
- [pipeline/improve.md](pipeline/improve.md) — CTO-grade continuous improvement cycle (`/improve`)
- [agents/AGENT_AGNOSTIC_GUIDE.md](agents/AGENT_AGNOSTIC_GUIDE.md) — shared contract
- 22 specialist agents under [agents/](agents) — see [Agent Inventory](#agent-inventory)

Local runtime:

- [scripts/run_pipeline.py](scripts/run_pipeline.py)
- [autonomous_pipeline/runner.py](autonomous_pipeline/runner.py)
- [autonomous_pipeline/adapters/](autonomous_pipeline/adapters)
- [autonomous_pipeline/specialists.py](autonomous_pipeline/specialists.py)
- [autonomous_pipeline/verification.py](autonomous_pipeline/verification.py)

Durable memory:

- [docs/agent-memory.md](docs/agent-memory.md)
- [autonomous_pipeline/memory/](autonomous_pipeline/memory)
- [scripts/validate_agent_memory.py](scripts/validate_agent_memory.py)

Host integration:

- [scripts/sync_prompt_pack.py](scripts/sync_prompt_pack.py)
- [autonomous_pipeline/host_sync.py](autonomous_pipeline/host_sync.py)
- generated host entrypoints such as `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`

## What Works Today

- canonical task model and run-state model
- `todo.json` adapter for local/offline execution
- GitHub Issues adapter for shared backlog execution
- resumable local run state in `.autonomous-state.json`
- artifact capture in `.runs/` or configured artifact directories
- `CODE_REVIEW` before `TEST`
- automated specialist execution for read-only analysis roles
- improvement capture into `agentMemory`
- sync into real Claude, Codex, and Gemini install directories

## What Does Not Work End To End Yet

- autonomous code authoring inside `DEV`
- bounded-write fixer execution
- fully automated branch, commit, and PR lifecycle for this repo exercised live from issue to merge
- dedicated structured runs database beyond local state/artifacts and `agentMemory`

## Pipeline

The source-of-truth pipeline policy is [pipeline/autonomous.md](pipeline/autonomous.md).

Important current behaviors:

- `CODE_REVIEW` runs before `TEST`
- code review enforces DRY, simplification, naming, style, docs/comments, and dependency concerns
- `todo.json` is a first-class local adapter
- GitHub Issues are the intended shared backlog for this repository
- lessons and patterns should be promoted into `agentMemory`

## Runtime Entry Points

Local runtime:

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root . --action full-demo
```

Agent memory validation:

```bash
PYTHONPATH=. python3 scripts/validate_agent_memory.py --project-path .
```

Host feature matrix:

```bash
PYTHONPATH=. python3 scripts/sync_prompt_pack.py print-host-features
```

## Host Sync

The Git repository is the distribution source for the prompt pack:

```text
https://github.com/metazen11/autonomous-agents.git
```

The local checkout at `~/_CODING/autonomous_agents_mds/` is the installed cache and working checkout. Agents should update the prompt pack through normal git workflow, then hosts install or fast-forward that repo before copying generated artifacts into Claude, Codex, Gemini, and Anvil. The portable control plane is the Python CLI; launchd, cron, and Windows Task Scheduler should call it as thin OS-specific schedulers.

Basic flow:

```bash
cp .env.example .env
python3 scripts/sync_prompt_pack.py check
python3 scripts/sync_prompt_pack.py sync
python3 scripts/sync_prompt_pack.py install-git-hooks
```

Fresh install or update from GitHub:

```bash
python3 scripts/sync_prompt_pack.py print-install-command --repo-root ~/_CODING/autonomous_agents_mds
```

Run the printed command to clone or fast-forward the prompt-pack checkout, then sync host installs.

Once the checkout exists, the OS-neutral update step is:

```bash
python3 scripts/sync_prompt_pack.py update-and-sync --repo-root ~/_CODING/autonomous_agents_mds
```

Agent inventory is centralized in two places:

- `agents/` for first-party workflow and delivery specialists
- `agent_bundles/<bundle>/agents/` for curated marketplace/plugin agents copied verbatim from their canonical source

Quick setup on another Mac:

```bash
mkdir -p ~/_CODING
git clone https://github.com/metazen11/autonomous-agents.git ~/_CODING/autonomous_agents_mds
cd ~/_CODING/autonomous_agents_mds
cp .env.example .env
python3 scripts/sync_prompt_pack.py update-and-sync --repo-root "$PWD"
```

After the first setup, the same `update-and-sync` command is the fast update path. Use launchd, cron, or Windows Task Scheduler only to run that Python command on a schedule.

The sync layer now supports:

- copied pipeline and specialist prompts
- host-native instruction entrypoints
- generated config snippets for hook or MCP wiring
- periodic scheduler output for `cron`, `anacron`, `launchd`, and Windows Task Scheduler

See [examples/host-sync.md](examples/host-sync.md).

## Host Coverage

Primary hosts wired today:

- Claude
- Codex
- Gemini

Additional modeled hosts:

- Cursor
- OpenClaw

The sync tool is path-based. It does not assume one host runtime is canonical.

## Task Sources

Current supported task sources:

- `todo.json`
- GitHub Issues

Design target:

- keep adapters cohesive so other task systems or databases can map into the same canonical task model
- avoid baking source-specific logic into the orchestration phases

## Durable Learning

The system is intended to improve itself through promotion:

1. run artifacts
2. pattern candidates
3. playbooks
4. scripts or packaged skills

This learning layer should live in `agentMemory`, not only in chat history.

## Anvil Direction

The current repo runtime is Python-first and local-first. The likely execution direction is:

- keep this repository as the workflow contract, adapters, docs, and sync layer
- use `anvil` as the actual code-writing execution engine for `DEV`

That integration direction is not complete in this repository yet, but it is the intended path for full autonomous code authoring.

## Agent Inventory

22 specialist agents organized by function:

### Delivery Pipeline (6 agents)
| Agent | Role | Mode |
|-------|------|------|
| [code-reviewer](agents/code-reviewer.md) | Correctness, DRY, naming, style, maintainability | read_only |
| [qa-tester](agents/qa-tester.md) | Test selection, behavioral verification, edge cases | read_only + exec |
| [quality-gate](agents/quality-gate.md) | Senior review gate — blocks vague/unsafe plans | read_only |
| [security-fixer](agents/security-fixer.md) | Bounded fix for audited vulnerabilities | bounded_write |
| [compliance-fixer](agents/compliance-fixer.md) | Bounded SOC 2/HIPAA remediation | bounded_write |
| [skill-promoter](agents/skill-promoter.md) | Mines repeated workflows, promotes to automation | read_only |

### Security & Compliance (4 agents)
| Agent | Role | Mode |
|-------|------|------|
| [security-auditor](agents/security-auditor.md) | OWASP Top 10, secrets, CSP, dependencies | read_only |
| [hipaa-auditor](agents/hipaa-auditor.md) | HIPAA technical safeguards (45 CFR 164.312) | read_only |
| [soc2-auditor](agents/soc2-auditor.md) | SOC 2 Type II Trust Services Criteria | read_only |
| [dep-auditor](agents/dep-auditor.md) | Dependency CVEs, licenses, supply chain risk | read_only |

### Infrastructure & Performance (3 agents)
| Agent | Role | Mode |
|-------|------|------|
| [infra-checker](agents/infra-checker.md) | Service health, certs, DNS, containers | read_only |
| [db-analyst](agents/db-analyst.md) | Query plans, indexes, migrations, connection pools | read_only |
| [perf-profiler](agents/perf-profiler.md) | Web vitals, bundle size, API latency, memory leaks | read_only |

### CTO Continuous Improvement (8 agents)
| Agent | Role | Mode |
|-------|------|------|
| [cto-self-eval](agents/cto-self-eval.md) | Code health, debt density, maturity scoring | read_only |
| [cto-arch-review](agents/cto-arch-review.md) | Service topology, complexity budget, simplification | read_only |
| [cto-security-posture](agents/cto-security-posture.md) | Real security vs theater, compliance readiness | read_only |
| [cto-test-quality](agents/cto-test-quality.md) | Test meaningfulness, coverage gaps, anti-patterns | read_only |
| [cto-dx-review](agents/cto-dx-review.md) | Onboarding friction, Makefile, error quality | read_only |
| [cto-dep-health](agents/cto-dep-health.md) | Supply chain risk, version currency, license audit | read_only |
| [cto-perf-review](agents/cto-perf-review.md) | Resource efficiency, query patterns, cost projection | read_only |
| [cto-parallel-work](agents/cto-parallel-work.md) | Task decomposition, conflict avoidance, isolation | read_only |

### Shared Contract
| File | Purpose |
|------|---------|
| [AGENT_AGNOSTIC_GUIDE](agents/AGENT_AGNOSTIC_GUIDE.md) | Operational responsibility model, handoff contract, memory integration |

### CTO Improvement Skill (`/improve`)

The [pipeline/improve.md](pipeline/improve.md) skill runs an 8-dimension self-evaluation:

1. **Codebase Health** — dead code, debt density, function complexity
2. **Architecture** — service count, complexity budget, simplification
3. **Security** — controls verified working (not just existing)
4. **Test Quality** — test meaningfulness, negative tests, coverage gaps
5. **Documentation** — freshness, accuracy, onboarding clarity
6. **Developer Experience** — time-to-productive, Makefile, error quality
7. **Performance** — resource utilization, query patterns, caching
8. **Dependencies** — version currency, CVEs, license compliance

Produces a scored scorecard with trend tracking. Run at end of every sprint or before releases.

---

## Repository Backlog

Public repo:

- `https://github.com/metazen11/autonomous-agents`

This repository should use GitHub Issues as its own productization backlog. The detailed implementation roadmap is still captured in [plan.txt](plan.txt).
