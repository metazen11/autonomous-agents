# Handoff

## Session Direction

The remaining implementation work for this session should move to the Anvil repository:

- `/Users/mz/Dropbox/_CODING/anvil`

Do not continue building the production planning, retrieval, FastAPI, MCP, CLI, or coding-agent runtime features in this repository.

## This Repository Owns

- agent-agnostic prompt pack
- workflow phase definitions
- specialist contracts
- architecture and integration documentation
- recorded examples

## Anvil Owns

- production execution runtime
- interactive coding harness
- FastAPI server
- MCP server
- tool registry
- worker loop
- shared planning and retrieval services

## Active Planning Spec

Use [planning-feature-plan.md](planning-feature-plan.md) as the implementation specification for the next phase of work.

That plan assumes:

- shared-service implementation first
- DRY boundaries across API, MCP, CLI, and tool layers
- Anvil as the primary execution platform
- this repository as the workflow/spec source of truth

## Current State

- `main` contains the refreshed example runs
- current local branch here is `planning-harness`
- the only intended change in this repository right now is the planning specification and this handoff note

## Next Step

Change working context to the Anvil repository and begin with:

1. auditing existing shared-service boundaries
2. defining canonical planning and retrieval interfaces
3. implementing the planning service first
