# Capture Buffer — Enablement Runbook

## Enable for a project

1. Set the tracker in the project's `.autonomous.json`:
   - todo.json (default): omit `task_source` or set `"task_source": "todo_json"`.
   - GitHub: `"task_source": "github"`, `"github_repo": "owner/name"`.
   - Asana: `"task_source": "asana"`, `"asana_project_gid": "<gid>"`,
     optionally `"asana_default_section_gid": "<gid>"`.
2. For Asana, export the PAT (never commit it):
   `export ASANA_ACCESS_TOKEN=...` (from the operator's Asana developer console).
3. Confirm the local mirror filename. New projects use `todo.json`. fire-map uses
   `tasks.json` — set `"todo_path": "tasks.json"` in `.autonomous.json` so the
   mirror writes to the existing file.

## fire-map (Fire Map Tech, Asana canonical)

`.autonomous.json` template:
```json
{
  "task_source": "asana",
  "asana_project_gid": "REPLACE_WITH_FIRE_MAP_TECH_GID",
  "todo_path": "tasks.json"
}
```
Fire Map Tech project + task gids are referenced in `fire-map.wfca.com/handoff.md`
and ADRs (e.g. task gid 1215642525150297). Confirm the *project* gid from the Asana
project URL before filling the template.

## Verify end state (Definition of Done)

- `/capture test capture — please ignore` → a new Asana task appears in Fire Map
  Tech AND a `ready` task appears in `tasks.json` with `source: "asana"` and a
  matching `metadata.tracker_ref`. Delete the test task afterward.
- The captured task is NOT `done` until `aa_auditor` verifies its acceptance
  criteria and closes the Asana task; `reconcile_done` then flips the local mirror.
