# Planning Feature Production Plan

## Purpose

Define a production-grade planning and retrieval feature set for the autonomous system, with Anvil as the execution platform and this repository as the workflow/specification source of truth.

This plan exists to prevent duplicated implementation across:

- FastAPI
- MCP
- CLI
- in-agent tools
- prompt-pack behavior

The target is one cohesive planning and retrieval system that can be invoked consistently by Codex, Claude, Gemini, Anvil, and any host that consumes the shared workflow contract.

## Scope

This feature covers:

- first-class planning and todo management
- local retrieval
- memory retrieval
- internet retrieval
- shared service boundaries
- CLI and interactive harness ergonomics
- FastAPI and MCP exposure
- integration into the autonomous pipeline

This feature does not, by itself, define:

- full autonomous code-authoring policy
- full PR/merge automation policy
- all specialist-agent implementations

Those remain adjacent tracks and must integrate with the planning layer rather than being embedded inside it.

## Production Goal

Deliver a planning and retrieval system that:

- persists task plans across turns and sessions
- supports explicit todo lifecycle management
- searches local workspace content deterministically
- searches durable memory before repeating known work
- searches the web when freshness or external documentation matters
- is implemented once in shared Python services
- is exposed consistently through FastAPI, MCP, CLI, and agent tools
- is safe, observable, resumable, and testable

## Architectural Decision

### Source Of Truth

- This repository remains the canonical source for:
  - workflow phases
  - role contracts
  - orchestration policy
  - examples and documentation
- Anvil becomes the canonical source for:
  - production execution runtime
  - interactive coding harness
  - FastAPI service surface
  - MCP server surface
  - local tool execution
  - worker-loop integration

### DRY Boundary

All new planning and retrieval logic must be implemented as shared Python services first.

Those shared services are then exposed through:

- agent tools
- CLI slash commands
- FastAPI endpoints
- MCP tool handlers

No interface-specific business logic should be introduced unless strictly necessary for transport adaptation.

## Functional Requirements

### Planning

The system must support:

- creating a structured plan for a task
- reading the current plan
- adding todo items
- updating todo item status
- recording blockers
- recording notes and rationale
- associating acceptance criteria with todo items
- associating ownership or role with todo items
- preserving plan state across iterations and sessions

### Local Retrieval

The system must support:

- exploring the workspace tree
- searching file names
- searching file contents
- reading targeted files
- returning bounded, deterministic results

### Memory Retrieval

The system must support:

- querying agent-memory for prior patterns, decisions, gotchas, and fixes
- using project scoping where available
- graceful degradation when memory is unavailable

### Internet Retrieval

The system must support:

- searching the web for fresh information
- fetching URL contents
- separating discovery from retrieval
- preserving source provenance
- capturing retrieval artifacts when used in autonomous execution

### Integration

The planning and retrieval feature must integrate with:

- autonomous phase flow:
  - INIT
  - PICK
  - PLAN
  - DEV
  - CODE_REVIEW
  - TEST
  - REVIEW
  - PR
  - REPORT
  - IMPROVE
- Anvil’s interactive harness
- Anvil’s FastAPI service
- Anvil’s MCP server
- the existing local tool system

## Non-Functional Requirements

### Reliability

- planning state must survive process interruption
- retrieval failure must degrade cleanly
- services must have explicit typed inputs and outputs
- retries must be bounded and intentional

### Safety

- web retrieval must not bypass command or file-safety policy
- URL fetching must respect output limits
- planning state must not expose secrets
- local search must stay confined to the workspace unless explicitly designed otherwise

### Observability

- planning changes should be recordable as artifacts when used in pipeline runs
- retrieval actions should be traceable in logs or run artifacts
- status must be inspectable through CLI and API surfaces

### Performance

- local search should prefer `rg` or equivalent indexed/fast search
- retrieval outputs must be capped before being fed back to models
- web fetching must use sane timeouts and truncation

## Shared Service Design

The Anvil implementation should introduce a shared service layer with modules conceptually equivalent to:

- `planning/service.py`
- `retrieval/local_search.py`
- `retrieval/memory_search.py`
- `retrieval/web_search.py`
- `retrieval/url_fetch.py`

Each service should expose typed request/response objects using the existing project style.

### Planning Service Contract

The planning service should support operations equivalent to:

- `create_plan(task, context)`
- `get_plan(session_id | task_id)`
- `replace_todos(plan_id, todos)`
- `add_todo(plan_id, todo)`
- `update_todo(plan_id, todo_id, patch)`
- `record_blocker(plan_id, todo_id, blocker)`
- `summarize_plan(plan_id)`

### Retrieval Service Contract

The retrieval layer should support operations equivalent to:

- `explore_tree(path, depth, filters)`
- `search_local(pattern, path, file_type, limit)`
- `search_memory(query, project, type, limit)`
- `search_web(query, limit, freshness, domains)`
- `fetch_url(url, mode, limit)`

## Data Model

The planning model should include:

- `plan_id`
- `session_id`
- `task_id`
- `title`
- `status`
- `summary`
- `todos`
- `created_at`
- `updated_at`

Each todo item should include:

- `id`
- `title`
- `status`
- `owner`
- `dependencies`
- `acceptance_criteria`
- `notes`
- `blockers`
- `artifacts`

Todo status should be explicit and finite:

- `pending`
- `in_progress`
- `blocked`
- `done`
- `cancelled`

## Interface Exposure

### Agent Tools

Expose at least:

- `write_todos`
- `read_plan`
- `search_local`
- `search_memory`
- `search_web`
- `fetch_url`

### CLI

Expose at least:

- `/plan`
- `/todo add <text>`
- `/todo done <id>`
- `/todo block <id> <reason>`
- `/search-local <pattern> [path]`
- `/search-web <query>`
- `/fetch <url>`

### FastAPI

Expose at least:

- `GET /api/plans/{id}`
- `POST /api/plans`
- `PATCH /api/plans/{id}`
- `POST /api/plans/{id}/todos`
- `PATCH /api/plans/{id}/todos/{todo_id}`
- `POST /api/retrieval/local-search`
- `POST /api/retrieval/memory-search`
- `POST /api/retrieval/web-search`
- `POST /api/retrieval/fetch-url`

### MCP

Expose at least:

- `anvil_plan_read`
- `anvil_plan_update`
- `anvil_search_local`
- `anvil_search_memory`
- `anvil_search_web`
- `anvil_fetch_url`

## Autonomous Pipeline Integration

### PLAN Phase

- generate or update the plan
- decompose the task into explicit todos
- store plan state before execution continues

### DEV Phase

- update todo state as work advances
- consult local and memory retrieval before internet retrieval

### CODE_REVIEW And TEST

- annotate relevant todos with findings, blockers, or completion evidence

### IMPROVE

- analyze whether planning structure or retrieval actions should be promoted into:
  - memory
  - playbooks
  - scripts
  - follow-up issues

## Implementation Sequence

### Phase 1: Service Boundary Audit

- inspect Anvil’s current:
  - tool registry
  - FastAPI endpoints
  - MCP handlers
  - CLI command and slash-command layer
  - graph/runtime integration
- identify existing reusable functionality
- identify duplicated behavior

### Phase 2: Shared Planning Service

- add plan/todo schema
- add persistent storage choice
- add planning service implementation
- add unit tests

### Phase 3: Shared Retrieval Services

- wrap existing local search as shared services
- wrap memory search as shared service
- add web search and URL fetch shared services
- add unit tests and failure-path tests

### Phase 4: Interface Exposure

- expose planning and retrieval through:
  - agent tools
  - CLI slash commands
  - FastAPI
  - MCP

### Phase 5: Autonomous Workflow Wiring

- wire PLAN phase to planning service
- wire DEV and REVIEW paths to retrieval policy
- capture artifacts and status changes

### Phase 6: End-To-End Validation

- interactive harness validation
- FastAPI endpoint validation
- MCP validation
- autonomous task-flow validation

## Testing Strategy

### Unit Tests

- plan schema validation
- todo lifecycle transitions
- local search service behavior
- memory search service behavior
- web search service behavior
- URL fetch truncation and failure handling

### Integration Tests

- CLI planning commands
- FastAPI planning endpoints
- MCP planning tools
- graph/runtime use of planning state
- autonomous phase progression with persisted plan state

### Live Validation

- interactive Anvil session using planning commands
- one-shot task run using planning and retrieval
- at least one autonomous pipeline task with recorded plan artifacts

## Done Criteria

This feature is done when:

- planning is persistent and first-class
- local, memory, and web retrieval are available through shared services
- CLI, FastAPI, MCP, and agent tools all use the same planning/retrieval core
- autonomous workflow phases can read and update plan state
- tests cover both happy path and degraded path behavior
- at least one end-to-end run is verified on the production Anvil path

## Handoff Target

Implementation work for this plan belongs in the Anvil repository, not in this repository.

This repository should only be updated as needed for:

- workflow contracts
- prompt-pack references
- architecture docs
- examples that demonstrate the production behavior after it exists in Anvil
