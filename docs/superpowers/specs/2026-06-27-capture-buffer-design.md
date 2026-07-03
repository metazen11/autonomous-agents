# Capture Buffer: request → project tracker → todo.json

> The tracker is **per-project** (GitHub issues, Asana, or `todo.json`-only), not
> hardcoded to GitHub. Capture routes to whichever tracker the project declares.

**Date:** 2026-06-27
**Status:** Design — approved pending spec review
**Owner:** mz@wfca.com
**Repo:** `autonomous_agents_mds` (prompt-pack source)

## Problem

When the operator barrages the active session with requests and questions while
it is already working on a task, two things go wrong today:

1. **Requests get dropped.** The live TodoWrite list is memory-constrained — it is
   summarized away as context grows. A request fired mid-task can vanish.
2. **The session context-switches off the current task** to service each
   interruption, fragmenting focused work.

This is a **capture buffer for the human side of the loop**. It is explicitly
**NOT** a replacement for the per-project autonomous pipeline. Each project still
runs its own autonomous agent pipeline that does the actual work. The capture
buffer's only job is to make sure that, under a barrage, every real request
becomes a durable, well-formed artifact that the existing pipeline can drain —
without the active session having to stop what it is doing.

## The three-layer queue (core idea)

| Layer | Durability | Role |
|---|---|---|
| **Project tracker** (GH issues, Asana, …) | Durable, cross-project | Canonical queue — **but the tracker is per-project, not hardcoded**. Each project declares its canonical tracker. The pipeline consumes it through a `TaskAdapter`. This is the **handoff seam**. |
| **`todo.json`** | Durable, local, survives context limits | Local mirror, tracker-independent. `TodoJsonAdapter` drains `status: "ready"` tasks. The tracker link rides in the existing `source`/`source_url` fields. |
| **TodoWrite** | Ephemeral, in-session | Live view shown to the operator this session. Summarized away — which is *why* the durable layers exist. |

### The tracker is a pluggable backend (not hardcoded to GitHub)

The canonical queue is **whatever tracker the project declares**, not GitHub
everywhere. Some projects live in GitHub issues; some live in Asana; some may only
use `todo.json`. Forcing 3–4 trackers on a team that already works from one is the
exact fragmentation this buffer exists to prevent. So capture routes to **one
canonical location per project — the project's own.**

This is not a new abstraction — the pipeline **already** has the seam:

- `autonomous_pipeline/adapters/base.py` defines `TaskAdapter` (`list_ready_tasks`,
  `get_task`, `claim_task`, `update_task`, `create_follow_up`).
- `adapters/todo_json.py` and `adapters/github.py` already implement it. The
  runner (`runner.py`) takes an **injected** adapter and is fully
  tracker-agnostic.
- An **Asana adapter** is simply another `TaskAdapter` implementation — same
  interface, different backend. Adding it does not touch capture or the runner.

**Adapter ≠ transport — the Asana MCP is the transport.** We already have the
Asana MCP (`mcp__asana__asana_create_task`, `asana_update_task`,
`asana_search_tasks`, …); we are **not** building a way to talk to Asana. The
`TaskAdapter` is a thin (~40-line) shim that translates the pipeline's five verbs
(`list_ready_tasks` / `get_task` / `claim_task` / `update_task` /
`create_follow_up`) into those MCP calls and maps an Asana task ↔ the `Task`
schema. It is small **because** the MCP does the heavy lifting. Its only job is to
keep the runner and capture from having to special-case "if Asana call these MCP
tools, if GitHub shell `gh`, if todo.json edit the file" — that special-casing is
exactly the coupling the seam removes. Same story for GitHub: the `gh` CLI is the
transport, `github.py` is the shim. So the Asana shim is warranted, but it is a
wrapper over the MCP you already have, not a new integration.

**Linkage requires no new format.** The `Task` schema already has `source` and
`source_url`. A captured task records `source: "<tracker>"` (`github`,
`asana`, `todo_json`) and `source_url: "<tracker item url>"`. A task written with
`status: "ready"` is *automatically* pipeline-eligible via
`list_ready_tasks()`, sorted by `priority` (`urgent` → `high` → `medium` →
`low`). The buffer feeds the existing drain; **zero new coupling**.

### One small gap to close: per-project tracker declaration

`todo.json` is the tracker we have actually been running on. It is the
**default backend** and the **home of the tracker declaration** — no new config
file. A project that has only `todo.json` (no GitHub, no Asana) is a first-class
canonical case, not a fallback.

The runner takes an injected adapter but there is **no per-project declaration**
of *which* adapter is canonical yet. Capture needs that. Add a `tracker` key to
the **header of the project's local task file** (`todo.json`, or `tasks.json`
where that is the existing name — see below):

```json
{
  "schema_version": "2",
  "tracker": "todo_json",   // "todo_json" (default) | "github" | "asana"
  "tracker_opts": { },       // e.g. {"repo": "owner/name"} or {"project_gid": "..."}
  "tasks": [ ... ]
}
```

Plus a tiny factory that maps the declared `tracker` to its `TaskAdapter`. Capture
and the runner both read this header so they agree on the canonical backend.
**Default when the key is absent: `todo_json`** — the mode we already run. When
`tracker` is `github`/`asana`, the local task file remains the durable mirror and
the named tracker is canonical.

**The local mirror filename is not hardcoded.** We standardize on `todo.json`, but
some live projects use a different name — fire-map's local file is **`tasks.json`**.
The declaration is found by looking for the project's task file
(`todo.json` first, then `tasks.json`), and the factory reads the `tracker` header
from whichever exists. New projects get `todo.json`; existing ones keep their
filename until migrated.

### Live Asana projects (why Asana is in scope now)

- **fire-map** (`fire-map.wfca.com`) — README line 18 states it explicitly:
  *"`tasks.json` — Lightweight task tracker (operational use; **Asana is the
  canonical project tracker**)."* Canonical project: **"Fire Map Tech"**, with
  real task gids in the handoff (e.g. `1215642525150297`, `1215857353204699`).
  fire-map is **already living this design by hand** — local file as operational
  mirror, Asana as canonical. Capture automates a workflow it already follows.
- **DailyDispatch** — also an Asana project per the operator.

For these, `tracker_opts` carries the Asana **project gid** (e.g. Fire Map Tech),
and a task's `tracker_ref` is the Asana task gid. This matches how the handoffs
already reference work.

## Default behavior: auto-file

Every barraged request that looks like work →

1. **immediately** becomes a well-formed item in the project's **canonical
   tracker** (a GH issue, an Asana task, … — durable from the first second),
2. a `ready` task appended to the target project's `todo.json` carrying the
   tracker item's `source`/`source_url`,
3. a mirrored TodoWrite item titled `#<ref> <title>` (`<ref>` = issue number or
   Asana task id, whichever the tracker uses).

Pure questions (no code change implied) are answered inline and **not** filed.
The active session keeps working on its current task throughout — capture is a
quick side-effect, not a context switch.

### Repo targeting

Capture files into the **repo the session is currently working in** by default.
The operator can override inline by naming another project (e.g.
`for etrade: add retry to the OAuth refresh`). No central-inbox indirection.

### Tracker-item authority

Tracker items are **auto-created, no confirmation gate** — honoring "nothing
dropped." The `tasker` subagent IS the specialized author: it does not dump the
operator's hurried one-liner into the tracker. It transforms garbage-in into a
well-formed tracker item (GH issue / Asana task):

- Clear, scoped title
- Acceptance criteria — testable and **auditor-verifiable against a live end
  state** (per the global CLAUDE.md Definition of Done). These are the exact
  checklist `aa_auditor` verifies before the issue may be closed.
- Testing requirements when the work warrants them
- Priority label and lane label
- Body that states intent and constraints

This applies the project's existing "an issue is not done until it has acceptance
criteria + auditor review + QA" standard **at creation time** — the tasker is the
quality gate at the front door.

## Components

### 1. `tasker` subagent — `agents/tasker.md`

Agent-agnostic contract, same house style as `reconciler.md` / `code-reviewer.md`
(reads `AGENT_AGNOSTIC_GUIDE.md` first).

**Inputs**
- `request` — the raw operator request text.
- `project` — target project. Defaults to the session's current project;
  overridden when the request names another (e.g. `for etrade: ...`).
- `priority` — optional; tasker infers `urgent/high/medium/low` from urgency
  language if omitted.
- `lane` — optional; tasker infers the lane/label from content if omitted.

**Procedure**
1. Classify: is this work (code change / investigation) or a pure question? Pure
   questions return `{filed: false, reason}` and are answered inline by the
   caller — the tasker files nothing.
2. **Resolve the project's canonical tracker** via the per-project declaration
   (`.autonomous.json` / `todo.json` header) → a `TaskAdapter` (GitHub, Asana, or
   `todo_json`).
3. Author a well-formed item body: title, acceptance criteria, testing
   requirements (if warranted), intent, constraints. (Tracker-neutral content;
   the adapter maps it to issue body / Asana notes.)
4. Create the item **through the resolved adapter** with priority + lane labels →
   capture the tracker `ref` (issue number / Asana gid) and `url`. When the
   canonical tracker *is* `todo_json`, this step is a no-op — the `todo.json` task
   itself is the canonical item.
5. Append a task to that project's `todo.json` in the **adapter schema shape**
   (`Task.from_dict`):
   ```json
   {
     "id": "<next id>",
     "title": "<title>",
     "body": "<one-line intent>",
     "status": "ready",
     "priority": "high|medium|low|urgent",
     "labels": ["<lane>"],
     "acceptance_criteria": ["..."],
     "source": "github | asana | todo_json",
     "source_url": "<tracker item url, if any>",
     "metadata": { "captured_at": "<iso>", "captured_by": "capture-buffer", "tracker_ref": "<ref>" }
   }
   ```
6. Return `{filed: true, tracker, ref, title, url}`.

**Allowed actions:** read project files; create/list items **through the resolved
`TaskAdapter`** (GitHub `gh`, Asana MCP, or todo.json); read/write the target
`todo.json`. No code edits, no pushes.

### 2. `/capture` skill — `skills/capture/skill.md`

User-invocable wrapper that runs the tasker.

- **`/capture <text>`** — force-capture the given text against the current
  project (routed to that project's declared tracker).
- **`/capture for <project>: <text>`** — force-capture against a named project.
- **Auto-capture** — the session auto-invokes the tasker for any barraged request
  that implies a code change, without the operator typing `/capture`. The
  operator only types `/capture` to force-file something that wouldn't otherwise
  trip the heuristic.

Skill is agent-agnostic in description; tool invocation (`Agent` / MCP subagent /
codex) is host-specific, matching the `/reconcile` skill's pattern.

### 3. Sync wiring

- `tasker.md` lives in `agents/` and is distributed by the **existing** agent
  discovery in `sync_prompt_pack.py` (`sync_agents_dir` / `discover_targets`). No
  script change required for the agent.
- The `/capture` skill is added to the synced skill set the same way `/reconcile`
  is.
- Verification: `python3 scripts/sync_prompt_pack.py check` lists `tasker` as a
  synced agent across hosts.

## Done convention (the auditor closes the ticket)

Done is **not** "the pipeline finished the code." Done is **the auditor verified
every acceptance criterion against the live end state with evidence and closed the
tracker item.** No self-certification, no sync pass guessing at done — the audit
gate is the single actor that transitions a tracker item to closed/complete. This
mirrors the CLAUDE.md Definition-of-Done contract exactly ("an issue is not marked
as done until an auditor agent has reviewed the work and a QA agent has tested the
UI"; "do not self-certify").

This is why the tasker authors testable acceptance criteria at the **front door**:
they are the exact checklist the `aa_auditor` verifies at the **back door**. The
front and back of the pipeline share one contract.

**Flow:**
1. Tasker files the tracker item with explicit, testable acceptance criteria →
   `todo.json` task `ready` → pipeline drains it → implementation lands.
2. Before reconcile, the **`aa_auditor`** runs against the originating tracker
   item. It checks EVERY acceptance criterion against the live end state and
   returns a per-criterion PASS/FAIL verdict with evidence.
   - **Any FAIL** → the auditor emits a structured fix list that re-enters the
     pipeline as follow-up work on the same item. The task stays `in_progress`.
     The item is **not** closed.
   - **All PASS** → the auditor is the actor that **closes the tracker item
     through the same `TaskAdapter`** (`gh issue close` / Asana complete), pasting
     the per-criterion evidence as the close comment. Closing via the adapter keeps
     the mechanism tracker-agnostic.
3. **Tracker-item close (by the auditor) is the done signal.** Only then does a
   capture/sync pass set the matching `todo.json` task `status: "done"` and mark
   the mirrored TodoWrite item completed.

- TodoWrite items titled `#<ref> <title>` → 1:1 with tracker items.
- The `todo.json` task never reaches `done` on the pipeline's say-so — only after
  an auditor-verified tracker-item close.
- UI work additionally requires the QA agent per CLAUDE.md; the auditor's PASS
  incorporates that QA evidence before closing.

## Schema evolution (we own this shape — update it)

The `todo.json` schema and the legacy tasks in it were created long ago. **We are
free to evolve the shape** rather than freeze it. The principle, across the board:
the schema is ours to change — when capture and the pipeline are better served by
a different shape, we update the canonical schema, update the `TodoJsonAdapter` to
match, and **migrate** the legacy tasks to the new shape in the same change.

For this feature that means:

1. **Canonical shape = the adapter's `Task` schema** (`status`, `priority` as
   `urgent/high/medium/low`, `source`, `source_url`, `acceptance_criteria`,
   `labels`, `metadata`). Capture writes this shape; the adapter already reads it.
2. **Migrate the two legacy tasks** in the prompt-pack `todo.json` from the old
   shape (`priority: "P1"`, `issue:`, `acceptance:`) to the canonical shape in the
   same change that lands capture. One-time, in-repo, reviewed.
3. **No long-lived normalizer.** Backward-compat shims are avoided; the file
   converges on one shape. (`Task.from_dict` already tolerates missing optional
   fields via defaults, so the migration is additive, not destructive.)
4. **Cross-project flexibility:** the same freedom applies to every project's
   `todo.json` — capture writes the canonical shape everywhere, and any legacy
   project file is migrated when capture first touches it.

This is simpler than the coexistence approach: one shape, one adapter, migrate
once.

## Reversibility

- The tasker and `/capture` skill are additive files; removing them reverts the
  feature with no schema change.
- Captured artifacts are ordinary tracker items (GH issues / Asana tasks) and
  ordinary `todo.json` `ready` tasks — both are already first-class in the
  pipeline, so nothing orphaned is left behind if the buffer is disabled.

## Out of scope (YAGNI)

- No central inbox repo / cross-repo router.
- No change to how the pipeline drains `ready` tasks — it already does.
- No new "done" daemon; done reconciliation piggybacks on capture/sync passes.
- **Adapter set for the first plan: `todo_json` + `github` + `asana`.** The first
  two already exist. **Asana is in scope now, not deferred** — fire-map and
  DailyDispatch are live Asana projects (see "Live Asana projects" below), so a
  buffer that can't route to Asana can't serve them. The Asana adapter is a thin
  `TaskAdapter` shim over the **Asana MCP we already have** (not a new
  integration).
