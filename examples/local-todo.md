# Local `todo.json` Example

This page shows the command sequence. For a checked-in sample run with inputs, outputs, and artifacts, see [local-todo-run/README.md](local-todo-run/README.md).

Recommended way to try it locally:

1. create a scratch directory inside your repo, for example `tmp/local-demo`
2. copy `examples/local-todo-run/.autonomous.json.example` to `tmp/local-demo/.autonomous.json`
3. copy `examples/local-todo-run/todo.before.json` to `tmp/local-demo/todo.json`
4. run the pipeline against that scratch directory

Create `.autonomous.json`:

```json
{
  "task_source": "todo_json",
  "todo_path": "todo.json",
  "artifacts_dir": ".runs",
  "development_command": "python3 -c \"print('dev ok')\"",
  "build_command": "python3 -c \"print('build ok')\"",
  "test_command": "python3 -c \"print('test ok')\""
}
```

Create `todo.json`:

```json
{
  "tasks": [
    {
      "id": "task-1",
      "title": "Exercise full local pipeline",
      "status": "ready",
      "source": "todo_json",
      "metadata": {
        "changed_files": ["autonomous_pipeline/runner.py"]
      }
    }
  ]
}
```

Run the full demo flow:

```bash
mkdir -p tmp/local-demo
cp examples/local-todo-run/.autonomous.json.example tmp/local-demo/.autonomous.json
cp examples/local-todo-run/todo.before.json tmp/local-demo/todo.json
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root tmp/local-demo --action full-demo --summary "local flow ok"
```

What it does:

- picks the task
- records planning
- runs `DEV`
- runs `CODE_REVIEW`
- runs verification
- runs automated review
- runs improvement promotion
- reports final status

Notes:

- the checked-in sample uses `sample-runs/` as a documentation-safe artifact directory; in normal usage you will usually use `.runs/` or `artifacts/`
- `full-demo` is a scaffolded end-to-end demo of the current runtime, not autonomous code-authoring
- in the current runtime, `changed_files` from task metadata is preserved when local git state is unavailable
