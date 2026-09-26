---
name: improve
description: "CTO-grade continuous improvement cycle. Runs self-evaluation across 8 dimensions, produces actionable findings, and tracks improvement velocity over time."
user_invocable: true
---

# /improve — Continuous Improvement Cycle

You are running a senior engineering improvement cycle. Think like a CTO who ships fast, cuts waste, and makes the team better — not busier. Every finding must be actionable. Every recommendation must earn its complexity.

## Mindset

- **Systems over symptoms.** Don't fix the bug — fix why the bug was possible.
- **Cut ruthlessly.** More code = more liability. If something can be removed, remove it.
- **Ship relentlessly.** Improvement that blocks shipping is not improvement.
- **Make the team better.** Automation, clarity, guardrails > heroic effort.
- **Measure or it didn't happen.** Every improvement cycle produces a scorecard.

## How It Works

`/improve` runs the 8 META checklists from `todo.json` as a structured evaluation. It produces a scorecard, surfaces the top 3 highest-leverage improvements, and optionally fixes them.

## Execution Flow

```
BASELINE → EVALUATE → SCORE → PRIORITIZE → FIX (optional) → RECORD
```

### 1. BASELINE — Know Where You Are

Before evaluating, capture the current state:

```bash
# Test health
pytest tests/ --tb=no -q 2>&1 | tail -5

# Codebase size
find . -name '*.py' -not -path './.volumes/*' -not -path './venv/*' | wc -l
cloc --by-file --include-lang=Python,SQL,YAML --quiet . 2>/dev/null | tail -3

# Service count
grep -c '^\s\+[a-z].*:$' docker-compose.yml 2>/dev/null || echo "no compose"

# Dependency count
wc -l < unification/requirements.txt 2>/dev/null || echo "no requirements"

# TODO/FIXME/HACK debt
grep -rn 'TODO\|FIXME\|HACK' --include='*.py' --include='*.html' --include='*.sql' . | grep -v '.volumes' | grep -v 'venv' | wc -l

# Git health
git status --short | wc -l
git stash list | wc -l
```

Record these as the baseline for the scorecard.

### 2. EVALUATE — Run All 8 Dimensions

Run each META checklist from `todo.json`. For each item, score as:
- **PASS** — meets the bar
- **WARN** — works but could be better
- **FAIL** — broken, missing, or actively harmful
- **SKIP** — not applicable right now

#### Dimension 1: Codebase Self-Evaluation (META-001)
```
Approach: Read code, don't guess. Run tests. Check for dead code, TODOs, hardcoded values.
Agent: Use grep, ast parsing, test runner output. Not vibes.
CTO lens: "If I hired a senior engineer tomorrow, would they be embarrassed by this code?"
```

#### Dimension 2: Architecture & Simplification (META-002)
```
Approach: Count services, measure memory, trace dependencies. Look for merges.
Agent: Parse docker-compose.yml, check resource limits, map networks.
CTO lens: "Am I paying for complexity I'm not using? Can I explain this to a board?"
```

#### Dimension 3: Security & Compliance (META-003)
```
Approach: Scan for secrets, verify RLS, check rate limits, audit logging.
Agent: grep for passwords/tokens, check migration files for RLS, verify decorators.
CTO lens: "If we got audited tomorrow, would we pass? If breached, what's the blast radius?"
```

#### Dimension 4: Test Quality & Coverage (META-004)
```
Approach: Count tests by type, check for behavior vs existence tests, run the suite.
Agent: Categorize tests, find untested modules, check negative test coverage.
CTO lens: "Do these tests catch real bugs, or do they just make the CI green?"
```

#### Dimension 5: Documentation Freshness (META-005)
```
Approach: Cross-reference docs against code reality. Check dates, commands, file lists.
Agent: Compare CLAUDE.md key files against actual files, try documented commands.
CTO lens: "Can a new engineer onboard from these docs alone, or will they DM me?"
```

#### Dimension 6: Developer Experience (META-006)
```
Approach: Time the critical path. Try onboarding steps. Check error messages.
Agent: Run make targets, check Makefile coverage, evaluate error output quality.
CTO lens: "How many minutes from git clone to running code? Under 10 or we're failing."
```

#### Dimension 7: Performance & Resources (META-007)
```
Approach: Check resource allocation vs usage, query patterns, cache effectiveness.
Agent: Parse compose memory limits, check for N+1 queries, review Prometheus config.
CTO lens: "Are we burning money on idle resources? Will this survive 10x load?"
```

#### Dimension 8: Dependency Health (META-008)
```
Approach: Check versions, scan for CVEs, verify all deps are used.
Agent: Parse requirements.txt, check pip-audit output, grep for unused imports.
CTO lens: "Is any dependency a ticking time bomb? Could we survive a supply chain attack?"
```

### 3. SCORE — Produce the Scorecard

Generate a structured scorecard:

```markdown
## Improvement Scorecard — [DATE]

| Dimension | Pass | Warn | Fail | Score | Trend |
|-----------|------|------|------|-------|-------|
| Codebase Health | 6 | 1 | 1 | 75% | -- |
| Architecture | 5 | 2 | 0 | 86% | -- |
| Security | 8 | 1 | 1 | 80% | -- |
| Test Quality | 5 | 2 | 1 | 69% | -- |
| Documentation | 6 | 1 | 1 | 75% | -- |
| Developer Experience | 7 | 1 | 0 | 94% | -- |
| Performance | 4 | 3 | 1 | 56% | -- |
| Dependencies | 6 | 1 | 1 | 75% | -- |
| **Overall** | | | | **76%** | -- |
```

Score = (PASS * 1.0 + WARN * 0.5) / (PASS + WARN + FAIL) * 100

Trend: Compare against previous scorecard in `docs/scorecards/` if one exists.
- Up arrow if improved 5+ points
- Down arrow if dropped 5+ points
- Dash if within 5 points

### 4. PRIORITIZE — Top 3 Highest-Leverage Fixes

From all FAIL and WARN items, rank by:

1. **Blast radius** — How many things break if this stays unfixed?
2. **Fix cost** — How long to fix? (Prefer < 30 min fixes)
3. **Compound interest** — Does fixing this prevent future issues?

Output exactly 3 recommendations:

```markdown
### Priority 1: [Title]
- **Dimension:** Security
- **Finding:** Access control policy missing on tenant-scoped table
- **Blast radius:** HIGH — cross-tenant data leak possible
- **Fix cost:** LOW — one migration file, 10 lines
- **Action:** Add row-level security policy or equivalent access control
```

### 5. FIX (Optional) — Act on Priority Items

If the user wants fixes applied:
- Fix Priority 1 first, verify, then move to Priority 2
- Each fix must include a test proving it works
- No fix without a rollback path
- Update the scorecard after fixes

### 6. RECORD — Save the Scorecard

Save the scorecard to `docs/scorecards/YYYY-MM-DD.md` for trend tracking.

If this is the first scorecard, create the directory:
```bash
mkdir -p docs/scorecards
```

Save a memory entry if any finding was surprising or non-obvious.

## Usage

```
/improve              # Full 8-dimension evaluation + scorecard
/improve security     # Single dimension deep-dive
/improve fix          # Evaluate + auto-fix top 3
/improve trend        # Show scorecard history and trends
```

## What This Is NOT

- Not a linter (use ruff/flake8 for that)
- Not a test runner (use pytest for that)
- Not a security scanner (use bandit/safety for that)
- Not a replacement for code review

This is the **meta-layer** — evaluating whether your linters, tests, scanners, and reviews are actually working. It's the CTO asking "are our processes catching the right things?" not "does this function have a bug?"

## Integration with Pipeline

`/improve` maps to the `IMPROVE` phase of the autonomous pipeline. Run it:
- At the end of every sprint (mandatory per CLAUDE.md)
- Before major releases
- When something feels off but you can't point to what
- After incidents or production issues
- Whenever you want to sanity-check the codebase

The scorecard becomes part of the sprint close deliverables alongside CHANGELOG, HANDOFF, and docs updates.
