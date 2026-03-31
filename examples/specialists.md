# Specialist Examples

For a checked-in sample run, see [specialist-dep-auditor-run/README.md](specialist-dep-auditor-run/README.md).

Recommended way to try it locally:

1. create a scratch directory inside your repo, for example `tmp/dep-auditor-demo`
2. copy `examples/specialist-dep-auditor-run/todo.before.json` to `tmp/dep-auditor-demo/todo.json`
3. run the specialist against that scratch directory

Run a specialist directly:

```bash
mkdir -p tmp/dep-auditor-demo
cp examples/specialist-dep-auditor-run/todo.before.json tmp/dep-auditor-demo/todo.json
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root tmp/dep-auditor-demo --action specialist-demo --specialist dep-auditor
```

Works with minimal task metadata:

- `code-reviewer`
- `qa-tester`
- `security-auditor`
- `dep-auditor`
- `db-analyst`
- `perf-profiler`
- `skill-promoter`

Requires extra metadata to be useful:

- `infra-checker`
- `soc2-auditor`
- `hipaa-auditor`

Partial or remediation-plan only today:

- `security-fixer`
- `compliance-fixer`

Notes:

- read-only specialists are the most complete runtime path today
- `infra-checker` needs `service_inventory` in task metadata
- `soc2-auditor` and `hipaa-auditor` need audit scope metadata
- fixer roles currently produce bounded remediation artifacts and explicit `needs_human` results
