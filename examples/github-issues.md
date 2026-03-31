# GitHub Issues Example

## Prerequisites

- `gh` CLI installed
- `gh` authenticated for the target repo
- the target repo already has the label you intend to use, for example `autonomous:ready`

Quick checks:

```bash
gh auth status
gh issue list --repo metazen11/autonomous-agents --limit 5
```

Create `.autonomous.json`:

```json
{
  "task_source": "github",
  "github_repo": "metazen11/autonomous-agents",
  "github_label": "autonomous:ready",
  "artifacts_dir": ".runs"
}
```

Pick a task:

```bash
PYTHONPATH=. python3 scripts/run_pipeline.py --repo-root . --action pick
```

Notes:

- GitHub Issues are the shared/public backlog
- local artifacts remain local
- progress is pushed back through adapter updates and comments
