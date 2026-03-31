# Specialist Contracts

Prompt files live under `agents/`.

Runtime-side specialist contracts live in:

- `autonomous_pipeline/specialists.py`

These contracts define:

- read-only versus bounded-write behavior
- required inputs
- optional inputs
- expected output keys
- escalation conditions

Current core specialists:

- `code-reviewer`
- `qa-tester`
- `security-auditor`
- `security-fixer`
- `dep-auditor`
- `db-analyst`
- `perf-profiler`
- `infra-checker`
- `soc2-auditor`
- `hipaa-auditor`
- `compliance-fixer`
- `skill-promoter`

