# CLI Control And TUI Follow-On Plan

## Purpose

Define the operator-control work needed in the Anvil CLI before building any TUI layer.

This plan exists because the current interactive harness can enter a bad iteration path without offering a reliable in-session escape mechanism other than process-level interruption.

## Current Diagnosis

The active interactive harness lives in the Anvil repository:

- `/Users/mz/Dropbox/_CODING/anvil/anvil/cli.py`
- `/Users/mz/Dropbox/_CODING/anvil/anvil/agent/runner.py`
- `/Users/mz/Dropbox/_CODING/anvil/anvil/middleware/base.py`
- `/Users/mz/Dropbox/_CODING/anvil/anvil/middleware/display.py`

Observed behavior:

- the REPL in `anvil/cli.py` blocks inside `run_agent(...)`
- the simple iterative runner in `anvil/agent/runner.py` has no cooperative stop or pause signal inside the iteration loop
- the operator cannot steer or halt a bad run at iteration boundaries
- `Ctrl-C` is the only practical interrupt path today
- `Ctrl-Z` suspends the shell job and is not a real loop-control mechanism

## Decision

Do not build a TUI first.

Build operator-safe CLI control primitives first, then layer a TUI on top of the same run-control surface.

The CLI remains the execution engine.
The TUI becomes an operator console for supervising multiple CLI-backed runs and sub-agents.

## CLI-First Goals

The CLI must support:

- cooperative stop after the current step or iteration
- pause before the next tool call or next iteration
- explicit resume
- skip current iteration when safe
- forced approval mode when drift is detected
- persisted run state and event history
- structured machine-readable events so another process can observe the run

## Target Operator Controls

Minimum controls:

- `Ctrl-C`: trigger controlled interrupt handling instead of abrupt loss of context
- `Esc`: request graceful stop at the next safe boundary
- `q`: request graceful stop at the next safe boundary
- `p`: pause before continuing
- `r`: resume a paused run
- `s`: skip current iteration if no tool is in flight
- `a`: switch to approval-required mode for subsequent actions

Clarification:

- `Esc` and `q` are interactive control intents, not shell signals
- if raw-key capture proves unreliable, slash commands such as `/pause`, `/resume`, `/stop`, and `/approve-on` are an acceptable first delivery

## Safe Boundaries

The runner should only stop automatically at explicit safe boundaries:

- before the next LLM call
- after the LLM response is received
- before a tool executes
- after a tool result returns
- at the end of an iteration

Do not interrupt in the middle of:

- file writes
- subprocess execution already dispatched
- database writes already in progress
- partially assembled tool-call state

## Required Runtime Changes In Anvil

### 1. Add Run Control State

Extend `RunState` in `anvil/middleware/base.py` with fields equivalent to:

- `run_id`
- `control_mode`
- `stop_requested`
- `pause_requested`
- `paused`
- `skip_iteration_requested`
- `approval_mode`
- `last_safe_boundary`
- `active_tool_name`
- `event_log_path`

### 2. Add Cooperative Checks To The Runner

Update `anvil/agent/runner.py` so the loop checks control flags:

- before `stack.arun_before(...)`
- after `chat_completion(...)`
- before each tool dispatch
- after each tool result
- at loop end

Requested outcomes:

- graceful stop returns a structured status such as `STOPPED`
- pause suspends progress without losing state
- skip iteration advances to the next turn with an explicit user-facing log entry

### 3. Add Structured Event Emission

Emit append-only run events for:

- run started
- iteration started
- llm responded
- tool starting
- tool finished
- pause requested
- paused
- resumed
- stop requested
- stopped
- approval mode changed
- run completed

First transport can be newline-delimited JSON written to a run-local event file.

### 4. Add CLI Control Entry Points

Update `anvil/cli.py` to support:

- `/pause`
- `/resume`
- `/stop`
- `/status`
- `/approve on`
- `/approve off`

If practical in the terminal stack, also add non-blocking key handling for:

- `Esc`
- `q`
- `p`
- `r`

If non-blocking key capture is too brittle for the first pass, prefer slash commands and a `Ctrl-C` interrupt menu.

### 5. Add Controlled KeyboardInterrupt Handling

When `Ctrl-C` occurs during an interactive run:

- do not immediately discard run context
- present a small action menu
- options should include `resume`, `stop`, `pause`, and `abort`

If the process cannot safely continue, persist enough state to allow inspection or resume.

### 6. Add Drift-Aware Auto-Pause

Add a lightweight guard that pauses when:

- the assistant repeatedly re-reads the same files
- the task objective changes materially
- the loop consumes multiple iterations without changing files or making forward progress

The first implementation can be heuristic and conservative.

## Acceptance Criteria For CLI Work

- the operator can stop a bad run without killing the entire terminal session
- a paused run preserves enough state to inspect what happened
- control changes are visible in the output and persisted in run artifacts
- a stopped run reports whether it stopped at a safe boundary
- verbose mode shows current iteration, active tool, and control state
- automated tests cover stop, pause, resume, and controlled interrupt paths

## TUI Follow-On Scope

Build the TUI only after the CLI primitives above are stable.

The TUI should not own execution logic. It should supervise multiple CLI-backed runs.

Primary TUI goals:

- launch multiple agent or sub-agent runs in parallel
- display status for each run
- show phase, iteration, active tool, and recent output
- pause or stop one run without affecting others
- surface approval-required and drift-paused runs
- attach to existing run IDs

## TUI Preconditions

Do not start TUI implementation until the CLI has:

- stable run IDs
- structured event files or an equivalent event stream
- cooperative pause and stop semantics
- resumable persisted state

## Suggested Delivery Order

1. Add `RunState` control fields and structured event emission.
2. Add cooperative checks to `anvil/agent/runner.py`.
3. Add slash-command controls in `anvil/cli.py`.
4. Add controlled `Ctrl-C` handling.
5. Add drift heuristics and approval-mode escalation.
6. Add a minimal TUI supervisor over the event stream.

## Notes

This repository should keep the workflow and operator plan.
Implementation of the actual CLI control path belongs in the Anvil repository per `handoff.md`.
