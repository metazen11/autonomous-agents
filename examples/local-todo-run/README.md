# Local `todo.json` Run Sample

This is a concrete checked-in sample of a local pipeline run.

## Inputs

- [.autonomous.json.example](.autonomous.json.example)
- [todo.before.json](todo.before.json)

## How To Reproduce

```bash
mkdir -p tmp/local-demo
cp examples/local-todo-run/.autonomous.json.example tmp/local-demo/.autonomous.json
cp examples/local-todo-run/todo.before.json tmp/local-demo/todo.json
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root tmp/local-demo --action full-demo --summary "local flow ok"
```

## Command

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root tmp/local-demo --action full-demo --summary "local flow ok"
```

## Outputs

- [full-demo-output.json](full-demo-output.json)
- [.autonomous-state.after.json](.autonomous-state.after.json)
- [todo.after.json](todo.after.json)

## Artifacts

- [plan-summary.txt](sample-run-001/plan-summary.txt)
- [development.log](sample-run-001/development.log)
- [verification-build.log](sample-run-001/verification-build.log)
- [verification-unit.log](sample-run-001/verification-unit.log)
- [code-reviewer-result.json](sample-run-001/code-reviewer-result.json)
- [skill-promoter-result.json](sample-run-001/skill-promoter-result.json)

## Notes

- This sample is from a real CLI execution, with repository-specific temp paths normalized into `<repo-root>/...`.
- The checked-in `sample-runs/` directory is documentation-only. In normal runtime usage you will usually configure `.runs/` or `artifacts/`.
- This sample ends in `done`; `CODE_REVIEW`, `TEST`, and `REVIEW` all passed on the current `main` branch.
- The sample input includes `changed_files`, and the current runtime preserves that metadata in scratch-directory runs.
