# `dep-auditor` Sample

This is a concrete checked-in sample of running a specialist directly.

## Input

- [todo.before.json](todo.before.json)

## How To Reproduce

```bash
mkdir -p tmp/dep-auditor-demo
cp examples/specialist-dep-auditor-run/todo.before.json tmp/dep-auditor-demo/todo.json
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root tmp/dep-auditor-demo --action specialist-demo --specialist dep-auditor
```

## Command

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root tmp/dep-auditor-demo --action specialist-demo --specialist dep-auditor
```

## Output

- [specialist-output.json](specialist-output.json)
- [dep-auditor-result.json](dep-auditor-result.json)

## Notes

- This sample is from a real CLI execution, with repository-specific temp paths normalized into `<repo-root>/...`.
- The direct specialist flow writes artifacts under `artifacts/` rather than `sample-runs/`.
